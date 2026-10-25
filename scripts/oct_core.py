#!/usr/bin/env python3
"""oct-toolkit shared core (0.5.3): auto first checkup, rolling no-nap baseline,
net nap saving, memory-bloat check. Stdlib only, no model calls, no network.

CLI:  oct_core.py <auto-checkup|report|baseline|refresh|memory-scan|memory-mark> [--cwd=PATH] [--days=N]
"""
import json
import os
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
OCT = CLAUDE_DIR / "oct-toolkit"
CHECKUP_F = OCT / "checkup.json"
CACHE_F = OCT / "session-cache.json"
MA_F = OCT / "baseline-ma.json"
NAP_EVENTS_F = OCT / "nap-events.jsonl"

# user-overridable in ~/.claude/oct-toolkit.json
DEFAULTS = {
    "first_checkup": True,
    "memory_check": True,
    "memory_max_lines": 80,
    "memory_max_tokens": 3000,
    "memory_check_days": 30,
    "baseline_window_sessions": 30,   # N: rolling window, newest N no-nap sessions per model
    "baseline_window_days": 60,       # ...and not older than this
    "baseline_min_sessions": 5,       # fewer than this per model -> no $ estimate
    "baseline_max_files": 400,        # scan cap per refresh
    "nudge_dynamic": True,            # nap reminder only when net saving > nudge_min_net_usd
    "nudge_min_net_usd": 0.02,
    "nap_fallback_remaining": 10,     # conservative remaining calls when history is thin
    "checkup_min_days": 3,
    "checkup_min_sessions": 3,
}
COLD_CALLS = 3          # first K calls of a session = cold start
MIN_LONGER = 5          # need this many longer sessions to use the history distribution
CK_DEFAULT = 2000       # checkpoint tokens injected after /clear when no nap history
MA_TTL_S = 6 * 3600
RETRY_S = 6 * 3600


# ---------- small io / config ----------
def read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json(p, d):
    try:
        p = Path(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp%d" % os.getpid())
        tmp.write_text(json.dumps(d), encoding="utf-8")
        os.replace(tmp, p)
    except Exception:
        pass


def _user_cfg():
    d = read_json(CLAUDE_DIR / "oct-toolkit.json")
    return d if isinstance(d, dict) else {}


def cfg(key):
    dflt = DEFAULTS[key]
    v = _user_cfg().get(key, dflt)
    if isinstance(dflt, bool):
        return bool(v)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else dflt


def cfg_has(key):
    v = _user_cfg().get(key)
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0


def spawn_bg(args):
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x08000000 | 0x00000200
    else:
        kw["start_new_session"] = True
    try:
        subprocess.Popen([sys.executable, str(HERE / "oct_core.py")] + list(args), **kw)
    except Exception:
        pass


_UA = None


def _ua():
    global _UA
    if _UA is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("usage_analyze_mod", str(HERE / "usage-analyze.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _UA = m
    return _UA


# ---------- per-session summaries (cached by path+mtime+size) ----------
_NUM = {k: re.compile(rb'"%s":(\d+)' % k.encode()) for k in
        ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens",
         "ephemeral_1h_input_tokens", "ephemeral_5m_input_tokens")}
_ID = re.compile(rb'"id":"(msg_[^"]+)"')
_MODEL = re.compile(rb'"model":"([^"]+)"')
_TS = re.compile(rb'"timestamp":"([^"]+)"')
_EP = re.compile(rb'"entrypoint":"([^"]+)"')
_FLAGS = (b"oct-toolkit auto-wake: the user just ran", b"<command-name>/oct-nap</command-name>",
          b"<command-name>/oct-toolkit:oct-nap</command-name>", b"run the /oct-nap background procedure")


def _n(rx, u):
    m = rx.search(u)
    return int(m.group(1)) if m else 0


def summarize(path, ua):
    msgs = {}
    flag = False
    users = 0
    ep = ""
    with open(path, "rb") as f:
        for line in f:
            if b'"type":"assistant"' in line:
                i = line.find(b'"usage":')
                if i < 0:
                    continue
                u = line[i:]
                m = _MODEL.search(line)
                t = _TS.search(line)
                if not m or not t:
                    continue
                mid = _ID.search(line)
                key = mid.group(1) if mid else len(msgs)
                if not ep:
                    e = _EP.search(line)
                    ep = e.group(1).decode() if e else ""
                msgs[key] = {"ts": t.group(1).decode(), "model": ua._norm_model(m.group(1).decode()),
                             "input": _n(_NUM["input_tokens"], u), "cache_read": _n(_NUM["cache_read_input_tokens"], u),
                             "cache_write": _n(_NUM["cache_creation_input_tokens"], u), "output": _n(_NUM["output_tokens"], u),
                             "cache_1h": _n(_NUM["ephemeral_1h_input_tokens"], u), "cache_5m": _n(_NUM["ephemeral_5m_input_tokens"], u)}
            else:
                if not flag and any(p in line for p in _FLAGS):
                    flag = True
                if (b'"type":"user"' in line and b'"tool_result"' not in line and b'"isMeta":true' not in line
                        and b'"isSidechain":true' not in line):
                    users += 1
    calls = sorted((c for c in msgs.values() if c["model"]), key=lambda c: c["ts"])
    out = {"n": len(calls), "u": users, "f": flag, "ep": ep, "e": calls[-1]["ts"] if calls else "",
           "m": calls[0]["model"] if calls else "", "h": {}}
    cold_cw, steady, steady_n = 0.0, 0.0, 0
    for i, c in enumerate(calls):
        cost = ua.calc_cost(c)
        p = ua.price_for(c["model"])
        cr = c["cache_read"] * p["cache_read"] / 1e6
        b = out["h"].setdefault(c["ts"][:13], [0.0, 0.0, 0])
        b[0] += cost
        b[1] += cr
        b[2] += 1
        if i < COLD_CALLS:
            if c["cache_1h"] or c["cache_5m"]:
                cold_cw += (c["cache_1h"] * p.get("cache_write_1h", p["cache_write"] * 2) + c["cache_5m"] * p["cache_write"]) / 1e6
            else:
                cold_cw += c["cache_write"] * p["cache_write"] / 1e6
        else:
            steady += cost
            steady_n += 1
    ctx = lambda c: c["input"] + c["cache_read"] + c["cache_write"]
    out.update(cold_cw=cold_cw, steady=steady, steady_n=steady_n,
               cold_ctx=ctx(calls[min(COLD_CALLS, len(calls)) - 1]) if calls else 0,
               end_ctx=ctx(calls[-1]) if calls else 0)
    for b in out["h"].values():
        b[0], b[1] = round(b[0], 6), round(b[1], 6)
    return out


def scan_all(deadline_s=90, max_age_days=None):
    """Update the per-file cache for recent files, newest first. Returns (total, done)."""
    ua = _ua()
    now = time.time()
    age = max_age_days or max(cfg("baseline_window_days"), 7)
    cutoff = now - age * 86400
    files = []
    try:
        for f in (CLAUDE_DIR / "projects").rglob("*.jsonl"):
            try:
                st = f.stat()
            except OSError:
                continue
            if st.st_mtime >= cutoff:
                files.append((st.st_mtime, st.st_size, f))
    except OSError:
        pass
    files.sort(key=lambda x: x[0], reverse=True)
    cache = read_json(CACHE_F) or {}
    keep = {}
    t_end = time.time() + deadline_s
    done = 0
    for mt, size, f in files:
        k = str(f)
        c = cache.get(k)
        if c and c.get("mt") == mt and c.get("size") == size:
            keep[k] = c
            done += 1
            continue
        if time.time() > t_end:
            if c:
                keep[k] = c
            continue
        try:
            s = summarize(f, ua)
        except OSError:
            continue
        s.update(mt=mt, size=size, sub=(f.parent.name == "subagents"))
        keep[k] = s
        done += 1
    write_json(CACHE_F, keep)
    return len(files), done


# ---------- A: week report ----------
def week_report(cache=None):
    cache = cache if cache is not None else (read_json(CACHE_F) or {})
    lo = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H")
    cost = cr = 0.0
    calls = 0
    sess, days = set(), set()
    for k, c in cache.items():
        hit = False
        for h, (a, b, n) in (c.get("h") or {}).items():
            if h >= lo:
                cost += a
                cr += b
                calls += n
                hit = True
                days.add(h[:10])
        if hit and not c.get("sub"):
            sess.add(k)
    return {"cost": cost, "cr": cr, "calls": calls, "sessions": len(sess), "days": len(days)}


# ---------- B: rolling no-nap baseline ----------
def baseline_build(cache=None):
    ua = _ua()
    cache = cache if cache is not None else (read_json(CACHE_F) or {})
    N = int(cfg("baseline_window_sessions"))
    lo = (datetime.now(timezone.utc) - timedelta(days=cfg("baseline_window_days"))).strftime("%Y-%m-%dT%H")
    by = {}
    for c in cache.values():
        if c.get("sub") or c.get("f") or c.get("ep") != "cli" or c.get("n", 0) < 2 or not c.get("m") or c.get("e", "") < lo:
            continue
        by.setdefault(c["m"], []).append(c)
    cks = []
    try:
        for ln in NAP_EVENTS_F.read_text(encoding="utf-8").splitlines():
            ck = json.loads(ln).get("ck")
            if isinstance(ck, (int, float)) and ck > 0:
                cks.append(ck)
    except Exception:
        pass
    ck = int(statistics.median(cks[-20:])) if len(cks) >= 3 else CK_DEFAULT
    models = {}
    for m, ss in by.items():
        ss.sort(key=lambda c: c["e"], reverse=True)
        ss = ss[:N]
        cold = [c for c in ss if c["n"] >= COLD_CALLS]
        st_n = sum(c["steady_n"] for c in ss)
        grow = [(c["end_ctx"] - c["cold_ctx"]) / (c["n"] - COLD_CALLS) for c in ss if c["n"] >= COLD_CALLS + 5]
        p = ua.price_for(m)
        models[m] = {
            "sessions": len(ss), "lens": sorted(c["n"] for c in ss),
            "calls_per_turn": (sum(c["n"] for c in ss) / max(1, sum(c["u"] for c in ss))),
            "cold_sessions": len(cold),
            "cold_cw": (sum(c["cold_cw"] for c in cold) / len(cold)) if cold else 0.0,
            "cold_ctx": (sum(c["cold_ctx"] for c in cold) / len(cold)) if cold else 0.0,
            "turn_cost": (sum(c["steady"] for c in ss) / st_n) if st_n else 0.0,
            "growth": statistics.median(grow) if grow else 0.0,
            "p_cr": p["cache_read"], "p_cw": p["cache_write"],
            "newest": ss[0]["e"], "oldest": ss[-1]["e"],
        }
    d = {"computed_at": time.time(), "window_sessions": N, "window_days": cfg("baseline_window_days"),
         "ck": ck, "models": models}
    write_json(MA_F, d)
    return d


def baseline_load():
    return read_json(MA_F)


def model_baseline(model, ma=None):
    ma = ma or baseline_load()
    if not ma:
        return None, None
    m = re.sub(r"-\d{8}$", "", model or "")
    b = (ma.get("models") or {}).get(m)
    if not b or b["sessions"] < cfg("baseline_min_sessions") or b["cold_sessions"] < 3 or b["cold_ctx"] <= 0:
        return None, ma
    return b, ma


def remaining_calls(b, t):
    longer = [L - t for L in b["lens"] if L > t]
    if len(longer) >= MIN_LONGER:
        return statistics.median(longer), "history"
    return float(cfg("nap_fallback_remaining")), "fallback"


def net_saving(b, ctx, t, ck=CK_DEFAULT):
    """Net $ saved by nap + /clear now. ctx = current context tokens, t = calls so far."""
    H, src = remaining_calls(b, t)
    cold_size = b["cold_ctx"] + ck
    gross = max(0.0, ctx - cold_size) * b["p_cr"] / 1e6 * H
    cold = b["cold_cw"] + ck * b["p_cw"] / 1e6
    return {"net": gross - cold, "gross": gross, "cold": cold, "H": H, "src": src, "sessions": b["sessions"]}


def breakeven_ctx(b, H, ck=CK_DEFAULT):
    return b["cold_ctx"] + ck + (b["cold_cw"] + ck * b["p_cw"] / 1e6) / (b["p_cr"] / 1e6 * H)


def suggest_every_turns(b, ck=CK_DEFAULT):
    g = b.get("growth") or 0
    if g <= 0:
        return None
    thr = cfg("nudge_min_net_usd")
    for t in range(COLD_CALLS + 1, 800):
        if net_saving(b, b["cold_ctx"] + g * t, t, ck)["net"] > thr:
            return max(1, round(t / max(1.0, b["calls_per_turn"])))
    return None


def fmt_usd(x):
    return ("-" if x < 0 else "") + ("$%.2f" if abs(x) >= 0.01 else "$%.3f") % abs(x)


def nap_net_line(model, ctx, ck, t):
    """Extra line for `--nap-savings`; '' when nothing honest can be said."""
    ma = baseline_load()
    if not ma:
        spawn_bg(["refresh"])
        return "(net $ estimate unavailable: your baseline is still being built in the background)"
    if time.time() - ma.get("computed_at", 0) > MA_TTL_S * 4:
        spawn_bg(["refresh"])
    b, _ = model_baseline(model, ma)
    if not b:
        return "(net $ estimate unavailable: fewer than %d comparable no-nap sessions for %s in your history)" % (
            cfg("baseline_min_sessions"), model or "this model")
    r = net_saving(b, ctx, t, ck)
    if r["src"] == "history":
        basis = "~%d more calls expected, median of your last %d sessions" % (r["H"], r["sessions"])
    else:
        basis = "assumes only ~%d more calls (thin history, kept conservative)" % r["H"]
    word = "saves" if r["net"] > 0 else "does not pay off:"
    return "estimate: nap+/clear %s net %s after ~%s cold start already deducted (%s)" % (
        word, fmt_usd(r["net"]), fmt_usd(r["cold"]), basis)


# ---------- C: memory ----------
def slug(cwd):
    return re.sub(r"[^A-Za-z0-9]", "-", cwd or os.getcwd())


def memory_dir(cwd=None):
    return CLAUDE_DIR / "projects" / slug(cwd) / "memory"


def memory_stats(cwd=None):
    d = memory_dir(cwd)
    try:
        txt = (d / "MEMORY.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return {"dir": str(d), "lines": len(txt.splitlines()), "tokens": len(txt) // 4,
            "files": len([f for f in d.glob("*.md") if f.name != "MEMORY.md"])}


def memory_nag(cwd=None):
    if not cfg("memory_check"):
        return None
    ms = memory_stats(cwd)
    if not ms:
        return None
    rec = read_json(CHECKUP_F) or {}
    mem = rec.setdefault("memory", {})
    s = slug(cwd)
    st = mem.setdefault(s, {})
    now = time.time()
    last = st.get("last_check") or rec.get("first_run_ts") or now
    big = ms["lines"] > cfg("memory_max_lines") or ms["tokens"] > cfg("memory_max_tokens")
    old = now - last > cfg("memory_check_days") * 86400
    if not (big or old):
        if st.get("alerted"):
            st["alerted"] = False
            write_json(CHECKUP_F, rec)
        return None
    if st.get("alerted"):
        return None
    st["alerted"] = True
    st["alerted_at"] = now
    write_json(CHECKUP_F, rec)
    if big:
        return ("oct-toolkit: MEMORY.md is %d lines (~%.1fk tokens; limit %d lines / %.1fk) and is read every session. "
                "Run /oct-checkup memory to find duplicates and stale notes." %
                (ms["lines"], ms["tokens"] / 1000, cfg("memory_max_lines"), cfg("memory_max_tokens") / 1000))
    return ("oct-toolkit: memory has not been checked for %d+ days (MEMORY.md %d lines). "
            "Run /oct-checkup memory for a tidy-up list." % (cfg("memory_check_days"), ms["lines"]))


def memory_mark(cwd=None):
    rec = read_json(CHECKUP_F) or {}
    st = rec.setdefault("memory", {}).setdefault(slug(cwd), {})
    st["last_check"] = time.time()
    ms = memory_stats(cwd)
    st["alerted"] = bool(ms and (ms["lines"] > cfg("memory_max_lines") or ms["tokens"] > cfg("memory_max_tokens")))
    write_json(CHECKUP_F, rec)


def memory_scan(cwd=None):
    d = memory_dir(cwd)
    ms = memory_stats(cwd)
    if not ms:
        print("No MEMORY.md found for this project at %s" % d)
        return
    rec = read_json(CHECKUP_F) or {}
    last = (rec.get("memory") or {}).get(slug(cwd), {}).get("last_check")
    print("memory dir: %s" % d)
    print("MEMORY.md: %d lines, ~%d tokens (thresholds: %d lines / %d tokens)" % (
        ms["lines"], ms["tokens"], cfg("memory_max_lines"), cfg("memory_max_tokens")))
    print("memory files: %d | last check: %s" % (ms["files"], datetime.fromtimestamp(last).strftime("%Y-%m-%d") if last else "never"))
    for f in sorted(d.glob("*.md")):
        if f.name != "MEMORY.md":
            st = f.stat()
            print("  %-48s %6d B  %s" % (f.name, st.st_size, datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d")))


# ---------- A: auto checkup ----------
def checkup_lines(cwd=None, partial=False):
    wk = week_report()
    ma = baseline_load() or {}
    ms = memory_stats(cwd)
    mn = cfg("checkup_min_days")
    if wk["days"] < mn or wk["sessions"] < cfg("checkup_min_sessions"):
        return "insufficient", ["oct-toolkit installed. Only %d day(s) / %d session(s) of history in the last 7 days; "
                                "the first report will appear automatically after a few days of use." % (wk["days"], wk["sessions"])]
    share = (wk["cr"] / wk["cost"] * 100) if wk["cost"] > 0 else 0
    l1 = ("oct-toolkit checkup (7 days): %s$%.0f API-equivalent across %d sessions; %.0f%% of it is re-reading long "
          "conversations (CR, cache reads)." % ("at least " if partial else "about ", wk["cost"], wk["sessions"], share))
    top = None
    for m, b in (ma.get("models") or {}).items():
        if top is None or b["sessions"] > top[1]["sessions"]:
            top = (m, b)
    b = model_baseline(top[0], ma)[0] if top else None
    every = suggest_every_turns(b, ma.get("ck", CK_DEFAULT)) if b else None
    parts = []
    if ms:
        parts.append("MEMORY.md is %d lines (~%.1fk tokens)%s" % (
            ms["lines"], ms["tokens"] / 1000,
            " - over the %d-line limit" % cfg("memory_max_lines") if ms["lines"] > cfg("memory_max_lines") else ""))
    parts.append(("napping about every %d turns pays off for you (%s)" % (every, top[0].replace("claude-", ""))) if every
                 else "not enough history yet to suggest a nap interval")
    return "done", [l1, "; ".join(parts)[0].upper() + "; ".join(parts)[1:] + ".", "For details run /oct-checkup."]


def auto_checkup_run(cwd=None):
    total, done = scan_all(deadline_s=100)
    baseline_build()
    status, lines = checkup_lines(cwd, done < total)
    rec = read_json(CHECKUP_F) or {}
    now = time.time()
    quiet = rec.get("status") == "insufficient" and status == "insufficient"   # do not repeat the same notice
    rec.update(status=status, lines=lines, last_run_ts=now, shown=quiet, files_total=total, files_done=done)
    rec.setdefault("first_run_ts", now)
    if status == "done":
        rec["done_ts"] = now
    write_json(CHECKUP_F, rec)


def auto_checkup_start(cwd=None):
    """SessionStart: first run when no record exists; retry while history is thin."""
    if not cfg("first_checkup"):
        return
    now = time.time()
    try:
        OCT.mkdir(parents=True, exist_ok=True)
        with open(CHECKUP_F, "x", encoding="utf-8") as f:
            json.dump({"status": "pending", "first_run_ts": now, "last_run_ts": now, "shown": True}, f)
        spawn_bg(["auto-checkup", "--cwd=" + (cwd or os.getcwd())])
        return
    except FileExistsError:
        pass
    except OSError:
        return
    rec = read_json(CHECKUP_F) or {}
    st = rec.get("status")
    if (st == "insufficient" and now - rec.get("last_run_ts", 0) > RETRY_S) or \
       (st == "pending" and now - rec.get("last_run_ts", 0) > 900):
        rec["last_run_ts"] = now
        write_json(CHECKUP_F, rec)
        spawn_bg(["auto-checkup", "--cwd=" + (cwd or os.getcwd())])


def pending_report_text():
    """Lines to show once (SessionStart or first Stop). Marks them shown."""
    if not cfg("first_checkup"):
        return ""
    rec = read_json(CHECKUP_F)
    if not rec or rec.get("shown", True) or rec.get("status") not in ("done", "insufficient") or not rec.get("lines"):
        return ""
    rec["shown"] = True
    write_json(CHECKUP_F, rec)
    return "\n".join(rec["lines"])


def ma_stale_refresh():
    ma = baseline_load()
    if not ma or time.time() - ma.get("computed_at", 0) > MA_TTL_S:
        spawn_bg(["refresh"])


# ---------- CLI printing ----------
def baseline_print():
    scan_all(deadline_s=30)
    ma = baseline_build()
    ck = ma["ck"]
    print("Rolling no-nap baseline (newest %d sessions per model, max %d days; sessions with nap//clear and automated runs excluded)" % (
        ma["window_sessions"], ma["window_days"]))
    print("checkpoint size used: ~%d tokens\n" % ck)
    if not ma["models"]:
        print("No comparable sessions yet.")
        return
    for m, b in sorted(ma["models"].items(), key=lambda x: -x[1]["sessions"]):
        ok = b["sessions"] >= cfg("baseline_min_sessions") and b["cold_sessions"] >= 3
        print("%s: %d sessions%s" % (m, b["sessions"], "" if ok else "  (too few for a $ estimate; need %d)" % cfg("baseline_min_sessions")))
        print("  cost per turn without nap (MA): $%.4f | session length median %d calls | context growth ~%.0f tokens/call" % (
            b["turn_cost"], statistics.median(b["lens"]), b["growth"]))
        print("  cold start (first %d calls): ~%dk tokens, CW $%.4f (+ checkpoint ~$%.4f)" % (
            COLD_CALLS, b["cold_ctx"] / 1000, b["cold_cw"], ck * b["p_cw"] / 1e6))
        if ok:
            be = ", ".join("%d calls left: %dk" % (h, breakeven_ctx(b, h, ck) / 1000) for h in (10, 25, 50))
            print("  break-even context (net saving > 0): " + be)
            ev = suggest_every_turns(b, ck)
            print("  suggested nap interval: %s" % ("about every %d turns" % ev if ev else "none (a nap never pays off at your session lengths)"))
        print()
    print("net saving = (context - cold start - checkpoint) x cache-read price x expected remaining calls - cold-start CW cost")


def report_print(cwd=None):
    total, done = scan_all(deadline_s=30)
    baseline_build()
    status, lines = checkup_lines(cwd, done < total)
    print("\n".join(lines))


def main():
    a = sys.argv[1:]
    if not a:
        return
    cwd = None
    for x in a[1:]:
        if x.startswith("--cwd="):
            cwd = x[6:]
    cmd = a[0]
    if cmd == "auto-checkup":
        auto_checkup_run(cwd)
    elif cmd == "refresh":
        scan_all(deadline_s=100)
        baseline_build()
    elif cmd == "baseline":
        baseline_print()
    elif cmd == "report":
        report_print(cwd)
    elif cmd == "memory-scan":
        memory_scan(cwd)
    elif cmd == "memory-mark":
        memory_mark(cwd)


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    main()
