#!/usr/bin/env python3

import io
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_BUILTIN_PRICES = {
    "claude-fable-5-1": {"input": 10.00, "cache_write": 12.500, "cache_write_1h": 20.00, "cache_read": 0.250, "output": 50.00},
    "claude-mythos-5-1": {"input": 10.00, "cache_write": 12.500, "cache_write_1h": 20.00, "cache_read": 0.250, "output": 50.00},
    "claude-fable-5": {"input": 10.00, "cache_write": 12.500, "cache_write_1h": 20.00, "cache_read": 1.000, "output": 50.00},
    "claude-mythos-5": {"input": 10.00, "cache_write": 12.500, "cache_write_1h": 20.00, "cache_read": 1.000, "output": 50.00},
    "claude-opus-5-5": {"input": 4.00, "cache_write": 5.000, "cache_write_1h": 8.00, "cache_read": 0.200, "output": 20.00},
    "claude-opus-5": {"input": 5.00, "cache_write": 6.250, "cache_write_1h": 10.00, "cache_read": 0.500, "output": 25.00},
    "claude-opus-4-8": {"input": 5.00, "cache_write": 6.250, "cache_write_1h": 10.00, "cache_read": 0.500, "output": 25.00},
    "claude-opus-4-7": {"input": 5.00, "cache_write": 6.250, "cache_write_1h": 10.00, "cache_read": 0.500, "output": 25.00},
    "claude-opus-4-6": {"input": 5.00, "cache_write": 6.250, "cache_write_1h": 10.00, "cache_read": 0.500, "output": 25.00},
    "claude-opus-4-5": {"input": 5.00, "cache_write": 6.250, "cache_write_1h": 10.00, "cache_read": 0.500, "output": 25.00},
    "claude-opus-4-1": {"input": 15.00, "cache_write": 18.750, "cache_write_1h": 30.00, "cache_read": 1.500, "output": 75.00},
    "claude-opus-4": {"input": 15.00, "cache_write": 18.750, "cache_write_1h": 30.00, "cache_read": 1.500, "output": 75.00},
    "claude-sonnet-5-5": {"input": 2.00, "cache_write": 2.500, "cache_write_1h": 4.00, "cache_read": 0.100, "output": 10.00},
    "claude-sonnet-5": {"input": 2.00, "cache_write": 2.500, "cache_write_1h": 4.00, "cache_read": 0.200, "output": 10.00},
    "claude-sonnet-4-6": {"input": 3.00, "cache_write": 3.750, "cache_write_1h": 6.00, "cache_read": 0.300, "output": 15.00},
    "claude-sonnet-4-5": {"input": 3.00, "cache_write": 3.750, "cache_write_1h": 6.00, "cache_read": 0.300, "output": 15.00},
    "claude-sonnet-4": {"input": 3.00, "cache_write": 3.750, "cache_write_1h": 6.00, "cache_read": 0.300, "output": 15.00},
    "claude-haiku-5-5": {"input": 0.10, "cache_write": 0.125, "cache_write_1h": 0.20, "cache_read": 0.010, "output": 0.50},
    "claude-haiku-4-5": {"input": 1.00, "cache_write": 1.250, "cache_write_1h": 2.00, "cache_read": 0.100, "output": 5.00},
}
_HAIKU_55_LONG = {"input": 0.50, "cache_write": 0.625, "cache_write_1h": 1.00, "cache_read": 0.05, "output": 2.50}
_HAIKU_55_LONG_AT = 100_000
_DEFAULT_PRICE = {"input": 3.00, "cache_write": 3.75, "cache_write_1h": 6.00, "cache_read": 0.30, "output": 15.00}

_CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
_CLAUDE_JSON = (_CLAUDE_DIR / ".claude.json") if os.environ.get("CLAUDE_CONFIG_DIR") else Path.home() / ".claude.json"

_PRICES_FILE = _CLAUDE_DIR / "scripts" / "prices.json"
_RATE_WINDOW_SECONDS = 20 * 60

_RL_STATE_FILE = _CLAUDE_DIR / "scripts" / "rate-limits-state.json"
_RL_STALE_SECONDS = 30 * 60

_FIVE_HOUR_MIN = 5 * 60
_SEVEN_DAY_MIN = 7 * 24 * 60

_SEVEN_D_THROTTLE_SECONDS = 3600
_SEVEN_D_WINDOW_SECONDS = 48 * 3600
_SEVEN_D_MIN_SPAN_SECONDS = 2 * 3600

_CTX_NUDGE_THRESHOLD = 50
_CTX_RATE_WINDOW_SECONDS = 15 * 60
_CTX_MIN_SPAN_SECONDS = 120
_CTX_NUDGE_ETA_MIN = 15
_CTX_HARD_FLOOR = 85

_ENTRY_FEE_FILE = _CLAUDE_DIR / "scripts" / "entry-fee-baseline.json"
_ENTRY_FEE_ALERT_PCT = 20

_TURN_COST_ALERT_MULT = 4
_TURN_COST_ALERT_FLOOR = 0.02

_TURN_COST_BASELINE_FILE = _CLAUDE_DIR / "scripts" / "turn-cost-baseline.json"
_TURN_COST_BASELINE_MAX_SAMPLES = 50

def _load_prices():
    prices = dict(_BUILTIN_PRICES)
    if _PRICES_FILE.exists():
        try:
            prices.update(json.loads(_PRICES_FILE.read_text()))
        except Exception:
            pass
    return prices

PRICES = _load_prices()

def find_session(session_id=None):
    projects = _CLAUDE_DIR / "projects"
    if session_id:
        for p in projects.rglob(f"{session_id}*.jsonl"):
            return p
        print(f"Session {session_id} not found")
        sys.exit(1)
    files = [f for f in projects.rglob("*.jsonl") if "subagents" not in f.parts]
    if not files:
        print("No sessions found")
        sys.exit(1)
    def _mt(f):
        try:
            return f.stat().st_mtime
        except OSError:
            return 0
    return max(files, key=_mt)

def _cfg_on(key):
    try:
        return bool(json.loads((_CLAUDE_DIR / "oct-toolkit.json").read_text(encoding="utf-8")).get(key, True))
    except Exception:
        return True

def _project_transcript():
    slug = re.sub(r"[^A-Za-z0-9]", "-", os.getcwd())
    files = list((_CLAUDE_DIR / "projects" / slug).glob("*.jsonl"))
    return max(files, key=lambda f: f.stat().st_mtime) if files else find_session()

def nap_savings(h):
    cp = _CLAUDE_DIR / "summaries" / f"{h}.md"
    calls = parse_calls(_project_transcript())
    if not calls or not cp.exists():
        return
    r = calls[-1]
    ctx = r["input"] + r["cache_read"] + r["cache_write"]
    ck = max(1, len(cp.read_text(encoding="utf-8", errors="replace")) // 4)
    if ctx <= ck:
        return
    _log_nap_event(h, r["model"], ctx, ck)
    k = lambda n: f"{n / 1000:.0f}k" if n >= 1000 else str(n)
    print(f"nap: context ~{k(ctx)} → ~{k(ck)} after /clear (~{round(100 * (1 - ck / ctx))}% less per turn)")
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import oct_core
        line = oct_core.nap_net_line(r["model"], ctx, ck, len(calls))
        if line:
            print(line)
    except Exception:
        pass

def tidy_check():
    if not _cfg_on("memory_tidy"):
        return
    slug = re.sub(r"[^A-Za-z0-9]", "-", os.getcwd())
    mem = _CLAUDE_DIR / "projects" / slug / "memory"
    try:
        n = len((mem / "MEMORY.md").read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return
    if n > 40:
        print(f"tidy: {n} lines in {mem}")

def wake_state():
    d = _CLAUDE_DIR / "summaries"
    def show(name, text):
        print(f"=== {name} ===")
        print(text.rstrip() if text.strip() else "(none)")
    rd = lambda f: f.read_text(encoding="utf-8", errors="replace") if f.exists() else ""
    show("index", rd(d / "index.md"))
    files = sorted(f.name for f in d.glob("*.md") if f.name != "index.md") if d.is_dir() else []
    show("files", chr(10).join(files))
    show("last woken", rd(d / ".last_woken"))

def stop_hook():
    extra = ""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import oct_core
        extra = oct_core.pending_report_text()
    except Exception:
        pass
    if not _cfg_on("cost_line"):
        if extra:
            print(json.dumps({"systemMessage": extra}))
        return
    time.sleep(1)
    cmd = [sys.executable, __file__, "--watch"]
    try:
        payload = {} if sys.stdin is None or sys.stdin.isatty() else json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    tp = payload.get("transcript_path")
    sid = payload.get("session_id")
    if tp and os.path.isfile(tp):
        cmd.append("--transcript=" + tp)
    elif sid and re.fullmatch(r"[0-9A-Za-z_-]+", str(sid)):
        cmd.append("--session=" + str(sid))
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = chr(10).join(x for x in (extra, (r.stdout or "").strip()) if x)
    if out:
        print(json.dumps({"systemMessage": out}))

def get_session_desc(path, max_msgs=3):
    snippets = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if len(snippets) >= max_msgs:
                    break
                try:
                    e = json.loads(line)
                    if e.get("type") == "user" and not e.get("isSidechain"):
                        content = e.get("message", {}).get("content", "")
                        text = get_text(content).strip().replace("\n", " ")
                        if text and not text.startswith("<"):
                            snippets.append(text[:35])
                except Exception:
                    continue
    except Exception:
        pass
    return "; ".join(snippets) if snippets else ""

def list_sessions(sort_by_cost=False, last_n=20, with_desc=False):
    projects = _CLAUDE_DIR / "projects"
    files = sorted(projects.rglob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    rows = []
    for f in files:
        calls = parse_calls(f)
        if not calls:
            continue
        cost = sum(calc_cost(r) for r in calls)
        date = calls[-1]["timestamp"][:10] if calls else "?"
        desc = get_session_desc(f) if with_desc else ""
        rows.append((f.stem[:8], date, len(calls), cost, desc))
    if sort_by_cost:
        rows.sort(key=lambda x: x[3], reverse=True)
    total = len(rows)
    rows = rows[:last_n]
    label = f"latest {len(rows)} of {total}" if total > last_n else f"{len(rows)} sessions"
    if with_desc:
        print(f"\n{'Session':<12}  {'Date':<10}  {'Calls':>5}  {'Cost':>8}  Description")
        print("─" * 80)
        for stem, date, n, cost, desc in rows:
            print(f"{stem:<12}  {date:<10}  {n:>5}  ${cost:.4f}  {desc}")
    else:
        print(f"\n{'Session':<12}  {'Date':<10}  {'Calls':>6}  {'Cost':>9}  {label}")
        print("─" * 44)
        for stem, date, n, cost, desc in rows:
            print(f"{stem:<12}  {date:<10}  {n:>6}  ${cost:.4f}")
    print()

def show_call(path, r):
    target_ts = r["timestamp"]
    entries = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    entries.sort(key=lambda e: e.get("timestamp", ""))

    target_idx = None
    for i, e in enumerate(entries):
        if e.get("type") == "assistant" and e.get("timestamp", "") == target_ts:
            target_idx = i
            break
    if target_idx is None:
        for i, e in enumerate(entries):
            if e.get("type") == "assistant" and e.get("timestamp", "")[:19] == target_ts[:19]:
                target_idx = i
                break
    if target_idx is None:
        print("Entry not found")
        return

    user_text = "(not found)"
    for i in range(target_idx - 1, -1, -1):
        e = entries[i]
        if e.get("type") == "user" and not e.get("isSidechain"):
            text = get_text(e.get("message", {}).get("content", ""))
            if text.strip():
                user_text = text
                break

    content = entries[target_idx].get("message", {}).get("content", [])
    asst_text = ""
    thinking_text = ""
    tool_uses = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                asst_text += block.get("text", "")
            elif btype == "thinking":
                thinking_text += block.get("thinking", "")
            elif btype == "tool_use":
                name = block.get("name", "?")
                inp = block.get("input", {})
                hint = ""
                if "command" in inp:
                    hint = inp["command"][:80]
                elif "file_path" in inp:
                    hint = inp["file_path"]
                tool_uses.append(f"{name}({hint})" if hint else name)
    elif isinstance(content, str):
        asst_text = content

    cost = calc_cost(r)
    ts = r["timestamp"][:19].replace("T", " ")
    print(f"\n── #{r.get('_idx','')} {ts}  {r['model']}  ${cost:.4f} ──")
    print(f"\n[User]\n{user_text[:600]}")
    if len(user_text) > 600:
        print(f"... ({len(user_text)} chars total)")
    if asst_text:
        print(f"\n[Assistant]\n{asst_text[:600]}")
        if len(asst_text) > 600:
            print(f"... ({len(asst_text)} chars total)")
    if tool_uses:
        print(f"\n[Tools]\n" + "\n".join(f"  {t}" for t in tool_uses))
    if thinking_text and not asst_text and not tool_uses:
        print(f"\n[Thinking]\n{thinking_text[:300]}...")
    if not asst_text and not tool_uses and not thinking_text:
        print("\n[Assistant] (no content)")
    print()

def parse_all_sessions(since_date=None):
    projects = _CLAUDE_DIR / "projects"
    files = sorted(projects.rglob("*.jsonl"), key=lambda f: f.stat().st_mtime)
    all_calls = []
    for f in files:
        calls = parse_calls(f)
        sid = f.stem[:8]
        is_sub = f.parent.name == "subagents"
        for r in calls:
            r["session"] = sid
            r["is_subagent"] = is_sub
        all_calls.extend(calls)
    all_calls.sort(key=lambda r: r["timestamp"])
    if since_date:
        all_calls = [r for r in all_calls if r["timestamp"] >= since_date + "T"]
    return all_calls

def get_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return block.get("text", "")
    return ""

def parse_calls(path):
    entries = []
    seen = set()
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                uid = e.get("uuid") or e.get("requestId")
                if uid and uid in seen:
                    continue
                if uid:
                    seen.add(uid)
                entries.append(e)
            except json.JSONDecodeError:
                continue

    entries.sort(key=lambda e: e.get("timestamp", ""))

    uuid_map = {e.get("uuid"): e for e in entries if e.get("uuid")}

    calls = []
    last_user_prompt = ""
    msg_index = {}

    for e in entries:
        t = e.get("type")

        if t == "user" and not e.get("isSidechain"):
            content = e.get("message", {}).get("content", "")
            if isinstance(content, list) and all(
                isinstance(b, dict) and b.get("type") != "text" for b in content
            ):
                continue
            prompt = get_text(content).replace("\n", " ").strip()
            if prompt:
                last_user_prompt = prompt

        elif t == "assistant":
            usage = e.get("message", {}).get("usage")
            if not usage:
                continue

            prompt = last_user_prompt
            if len(prompt) > 40:
                prompt = prompt[:37] + "..."

            cc  = usage.get("cache_creation", {})
            stu = usage.get("server_tool_use", {})

            mid = e.get("message", {}).get("id")
            call = {
                "timestamp":   e.get("timestamp", ""),
                "session":     "",
                "prompt":      prompt,
                "model":       e.get("message", {}).get("model", ""),
                "input":       usage.get("input_tokens", 0),
                "cache_read":  usage.get("cache_read_input_tokens", 0),
                "cache_write": usage.get("cache_creation_input_tokens", 0),
                "output":      usage.get("output_tokens", 0),
                "cache_1h":    cc.get("ephemeral_1h_input_tokens", 0),
                "cache_5m":    cc.get("ephemeral_5m_input_tokens", 0),
                "web_search":  stu.get("web_search_requests", 0),
                "web_fetch":   stu.get("web_fetch_requests", 0),
                "tier":        usage.get("service_tier", "n/a"),
                "speed":       usage.get("speed", "n/a"),
                "geo":         usage.get("inference_geo", "n/a"),
                "entrypoint":  e.get("entrypoint", ""),
            }
            if mid and mid in msg_index:
                calls[msg_index[mid]] = call
            else:
                if mid:
                    msg_index[mid] = len(calls)
                calls.append(call)

    return calls

def _turn_start_ts(path):
    """Timestamp of the last real (non tool_result) user message in a main transcript."""
    last = ""
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("type") != "user" or e.get("isSidechain") or e.get("isMeta"):
                continue
            c = e.get("message", {}).get("content", "")
            if isinstance(c, list) and all(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                continue
            ts = e.get("timestamp", "")
            if ts > last:
                last = ts
    return last

def turn_calls(path):
    """(main_calls, subagent_calls) for the latest turn; message ids already de-duplicated."""
    since = _turn_start_ts(path)
    main = [c for c in parse_calls(path) if c["timestamp"] >= since]
    subs = []
    sub_dir = path.parent / path.stem / "subagents"
    if sub_dir.is_dir() and main:
        for sf in sorted(sub_dir.glob("*.jsonl")):
            try:
                subs.extend(c for c in parse_calls(sf) if c["timestamp"] >= since)
            except OSError:
                pass
    return main, subs

def sum_calls(calls):
    t = {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0, "cost": 0.0,
         "c_input": 0.0, "c_cache_read": 0.0, "c_cache_write": 0.0, "c_output": 0.0}
    M = 1_000_000
    for r in calls:
        p = price_for(r.get("model", ""))
        for k in ("input", "cache_read", "cache_write", "output"):
            t[k] += r[k]
            t["c_" + k] += r[k] * p[k] / M
        t["cost"] += calc_cost(r)
    return t

def reflect_stats_compute(calls):
    if not calls:
        return {
            "total_cost": 0, "total_calls": 0, "session_count": 0,
            "subagent_calls": 0, "long_ctx_sessions": 0, "max_ctx_tokens": 0,
            "period_from": None, "period_to": None,
        }
    sessions = {}
    for r in calls:
        sid = r["session"] + ("_sub" if r.get("is_subagent") else "_main")
        ctx = r["input"] + r["cache_read"]
        if sid not in sessions:
            sessions[sid] = {"max_ctx": 0}
        sessions[sid]["max_ctx"] = max(sessions[sid]["max_ctx"], ctx)
    total_cost = sum(calc_cost(r) for r in calls)
    subagent_calls = sum(1 for r in calls if r.get("is_subagent"))
    long_ctx_sessions = sum(1 for s in sessions.values() if s["max_ctx"] > 150_000)
    max_ctx = max((s["max_ctx"] for s in sessions.values()), default=0)
    return {
        "total_cost": round(total_cost, 4),
        "total_calls": len(calls),
        "session_count": len(sessions),
        "subagent_calls": subagent_calls,
        "long_ctx_sessions": long_ctx_sessions,
        "max_ctx_tokens": max_ctx,
        "period_from": calls[0]["timestamp"][:10],
        "period_to": calls[-1]["timestamp"][:10],
    }

def _load_rl_state():
    if _RL_STATE_FILE.exists():
        try:
            return json.loads(_RL_STATE_FILE.read_text())
        except Exception:
            pass
    return {"updated_at": None, "five_hour": None, "seven_day": None, "history": [], "history_7d": [],
            "ctx_history_by_session": {}}

def _save_rl_state(state):
    try:
        _RL_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _RL_STATE_FILE.write_text(json.dumps(state))
    except Exception:
        pass

def statusline_hook():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    rl = data.get("rate_limits") or {}
    five = rl.get("five_hour")
    seven = rl.get("seven_day")

    now = datetime.now(timezone.utc)
    state = _load_rl_state()

    if five and five.get("used_percentage") is not None:
        hist = state.get("history", [])
        if not hist or (now - datetime.fromisoformat(hist[-1][0])) >= timedelta(seconds=60):
            hist.append([now.isoformat(), five["used_percentage"]])
        cutoff = now - timedelta(seconds=_RATE_WINDOW_SECONDS)
        hist = [[t, p] for t, p in hist if datetime.fromisoformat(t) >= cutoff]
        state["history"] = hist
        state["five_hour"] = five

    if seven and seven.get("used_percentage") is not None:
        hist7 = state.get("history_7d", [])
        if not hist7 or (now - datetime.fromisoformat(hist7[-1][0])) >= timedelta(seconds=_SEVEN_D_THROTTLE_SECONDS):
            hist7.append([now.isoformat(), seven["used_percentage"]])
        cutoff7 = now - timedelta(seconds=_SEVEN_D_WINDOW_SECONDS)
        hist7 = [[t, p] for t, p in hist7 if datetime.fromisoformat(t) >= cutoff7]
        state["history_7d"] = hist7
        state["seven_day"] = seven

    state["updated_at"] = now.isoformat()
    _save_rl_state(state)

    model_name = (data.get("model") or {}).get("display_name", "")
    ctx_pct = (data.get("context_window") or {}).get("used_percentage")
    session_id = data.get("session_id")

    if ctx_pct is not None:
        by_session = state.get("ctx_history_by_session", {})
        key = session_id or "_unknown"
        ctx_hist = by_session.get(key, [])
        if not ctx_hist or (now - datetime.fromisoformat(ctx_hist[-1][0])) >= timedelta(seconds=30):
            ctx_hist.append([now.isoformat(), ctx_pct])
        ctx_cutoff = now - timedelta(seconds=_CTX_RATE_WINDOW_SECONDS)
        ctx_hist = [[t, p] for t, p in ctx_hist if datetime.fromisoformat(t) >= ctx_cutoff]
        by_session[key] = ctx_hist
        by_session = {k: v for k, v in by_session.items()
                      if v and datetime.fromisoformat(v[-1][0]) >= ctx_cutoff}
        state["ctx_history_by_session"] = by_session
        state.pop("ctx_history", None)
        _save_rl_state(state)

    compact = _pulse_compact(state, now, session_id)
    line = f"{model_name}  {compact}" if model_name and compact else (compact or model_name)
    badge = savings_badge()
    print(f"{line}  {badge}" if badge else line)

_ICON_RANK = {"🔋": 0, "⚡": 1, "🪫": 2}
_MIN_DEFICIT_MINUTES = 15

_SURPLUS_MARGIN = 0.5
_SURPLUS_MARGIN_HIGH = 1.5

def _margin_icon(pct, remain_min, eta_min, margin_frac):
    if margin_frac is None or margin_frac >= 0 or pct <= 60:
        return "🔋"
    if remain_min - eta_min < _MIN_DEFICIT_MINUTES:
        return "🔋"
    return "⚡" if margin_frac >= -0.5 else "🪫"

def _battery(eta_str, margin_frac, icon, half_width=2):
    if margin_frac is None:
        return "│" + (f" {eta_str}" if eta_str else "")
    n = round(min(1.0, abs(margin_frac)) * half_width)
    dashes = "─" * n
    if margin_frac >= 0:
        return f"│{dashes}{eta_str}{icon}"
    return f"{icon}{eta_str}{dashes}│"

def _fmt_minutes(m):
    if m < 60:
        return f"{m:.0f}m"
    if m < 1440:
        return f"{m/60:.1f}h"
    return f"{m/1440:.1f}d"

def _ctx_eta_minutes(hist, now):
    if len(hist) < 2:
        return None
    t0, p0 = hist[0]
    span_min = (now - datetime.fromisoformat(t0)).total_seconds() / 60
    if span_min * 60 < _CTX_MIN_SPAN_SECONDS:
        return None
    _, p1 = hist[-1]
    rate = (p1 - p0) / span_min
    if rate <= 1e-6:
        return None
    return (100 - p1) / rate

def _avg_pace_eta_min(pct, remain_min, window_total_min):
    if remain_min is None or pct <= 0:
        return None
    elapsed_min = window_total_min - remain_min
    if elapsed_min < 1:
        return None
    avg_rate = pct / elapsed_min
    if avg_rate <= 1e-9:
        return None
    return (100 - pct) / avg_rate

def _reset_eta_raw(pct, resets_at, hist, now, min_span_min):
    remain_min = None
    if resets_at:
        reset_dt = datetime.fromtimestamp(resets_at, tz=timezone.utc)
        m = (reset_dt - now).total_seconds() / 60
        if m > 0:
            remain_min = m

    eta_min = None
    eta_note = "⏳"
    if len(hist) >= 2:
        t0, p0 = hist[0]
        span_min = (now - datetime.fromisoformat(t0)).total_seconds() / 60
        if span_min < min_span_min:
            wait_min = min_span_min - span_min
            eta_note = f"⏳{_fmt_minutes(wait_min)}"
        else:
            rate = (pct - p0) / span_min
            if rate <= 1e-6:
                eta_note = "∞"
            else:
                eta_min = (100 - pct) / rate

    return remain_min, eta_min, eta_note

def _surplus_tier(margin_frac):
    if margin_frac is None:
        return 0
    if margin_frac >= _SURPLUS_MARGIN_HIGH:
        return 2
    if margin_frac >= _SURPLUS_MARGIN:
        return 1
    return 0

def _rate_windows(state, now):
    updated_at = state.get("updated_at")
    if not updated_at:
        return []
    if now - datetime.fromisoformat(updated_at) > timedelta(seconds=_RL_STALE_SECONDS):
        return []
    five = state.get("five_hour")
    if not five or five.get("used_percentage") is None:
        return []

    windows = []

    def add_window(label, pct, resets_at, hist, min_span_min, window_total_min, check_surplus=False):
        remain_min, eta_recent_min, eta_note = _reset_eta_raw(
            pct, resets_at, hist, now, min_span_min
        )
        eta_avg_min = _avg_pace_eta_min(pct, remain_min, window_total_min)
        if eta_recent_min is not None and eta_avg_min is not None:
            eta_min = max(eta_recent_min, eta_avg_min)
        else:
            eta_min = eta_recent_min if eta_recent_min is not None else eta_avg_min

        margin_frac = None
        if remain_min is not None and eta_min is not None and remain_min > 1e-9:
            margin_frac = (eta_min - remain_min) / remain_min
        icon = _margin_icon(pct, remain_min, eta_min, margin_frac)
        eta_str = _fmt_minutes(eta_min) if eta_min is not None else eta_note

        surplus_tier = 0
        if check_surplus and eta_recent_min is not None and eta_avg_min is not None:
            surplus_eta_min = min(eta_recent_min, eta_avg_min)
            surplus_margin_frac = None
            if remain_min is not None and remain_min > 1e-9:
                surplus_margin_frac = (surplus_eta_min - remain_min) / remain_min
            surplus_tier = _surplus_tier(surplus_margin_frac)

        windows.append({
            "label": label, "pct": pct, "icon": icon, "eta_str": eta_str,
            "remain_str": _fmt_minutes(remain_min) if remain_min is not None else "?",
            "bar": _battery(eta_str, margin_frac, icon),
            "surplus": surplus_tier > 0, "surplus_tier": surplus_tier,
        })

    add_window("5h", five["used_percentage"], five.get("resets_at"), state.get("history", []), min_span_min=3, window_total_min=_FIVE_HOUR_MIN)

    seven = state.get("seven_day")
    if seven and seven.get("used_percentage") is not None:
        add_window("7d", seven["used_percentage"], seven.get("resets_at"), state.get("history_7d", []), min_span_min=120, window_total_min=_SEVEN_DAY_MIN, check_surplus=True)

    return windows

def _ctx_history_for(state, session_id):
    by_session = state.get("ctx_history_by_session", {})
    if session_id and session_id in by_session:
        return by_session[session_id]
    if not by_session:
        return state.get("ctx_history", [])
    return max(by_session.values(), key=lambda h: h[-1][0] if h else "")

def _ctx_nudge(state, now, session_id=None):
    ctx_hist = _ctx_history_for(state, session_id)
    if not ctx_hist:
        return False, None
    ctx_pct = ctx_hist[-1][1]
    eta_min = _ctx_eta_minutes(ctx_hist, now)
    if ctx_pct >= _CTX_HARD_FLOOR:
        return True, ctx_pct
    if ctx_pct >= _CTX_NUDGE_THRESHOLD and eta_min is not None and eta_min < _CTX_NUDGE_ETA_MIN:
        return True, ctx_pct
    return False, ctx_pct

def _pulse_compact(state, now, session_id=None):
    windows = _rate_windows(state, now)
    rate_part = "  ".join(
        f"{w['label']} {w['remain_str']}{w['icon']}{w['eta_str']}{'✨' if w.get('surplus') else ''}"
        for w in windows
    )

    ctx_nudge, ctx_pct = _ctx_nudge(state, now, session_id)
    ctx_part = f"🧠{ctx_pct:.0f}%{'💡' if ctx_nudge else ''}" if ctx_pct is not None else ""

    return "  ".join(p for p in (rate_part, ctx_part) if p)

def _worst_rate_icon(windows):
    if not windows:
        return "🔋"
    return max((w["icon"] for w in windows), key=lambda i: _ICON_RANK[i])

def pulse_detail():
    state = _load_rl_state()
    updated_at = state.get("updated_at")
    if not updated_at:
        print("No data yet. Let the statusLine refresh once (e.g. switch windows), then re-run.")
        return
    now = datetime.now(timezone.utc)
    if now - datetime.fromisoformat(updated_at) > timedelta(seconds=_RL_STALE_SECONDS):
        print("Data is stale (statusLine has not refreshed in over 30 minutes). Switch windows to refresh it, then re-run.")
        return

    windows = _rate_windows(state, now)
    rate_icon = _worst_rate_icon(windows)
    ctx_nudge, ctx_pct = _ctx_nudge(state, now)
    surplus_tier = max((w.get("surplus_tier", 0) for w in windows), default=0)

    verdict = {
        "🪫": "a window is burning far faster than schedule; slow down now",
        "⚡": "a window is burning faster than schedule; watch your pace",
        "🔋": "all quotas are on schedule",
    }[rate_icon]
    if ctx_nudge:
        verdict += "; ctx is high, run /oct-nap before wrapping up"
    if surplus_tier == 2:
        verdict += "; plenty of 7d quota left unused, so using the most expensive model costs you nothing"
    elif surplus_tier == 1:
        verdict += "; 7d quota has headroom, consider moving up a model tier"

    print(f"{'✨' if surplus_tier else ''}{rate_icon}{'💡' if ctx_nudge else ''} {verdict}")
    if ctx_pct is not None:
        print(f"ctx:{ctx_pct:.0f}%")
    if windows:
        print("  ".join(f"{w['label']} {w['pct']:.0f}%{w['bar']}" for w in windows))

_MODEL_DATE_SUFFIX_RE = re.compile(r"-\d{8}$")

_MODEL_RE = re.compile(r"^claude-(opus|sonnet|haiku|fable|mythos)-(\d+(?:-\d{1,2})?)(?:-|$)")

def _ver(v):
    return tuple(int(x) for x in v.split("-"))

def price_for(model):
    if model in PRICES:
        return PRICES[model]
    base = _MODEL_DATE_SUFFIX_RE.sub("", model)
    if base in PRICES:
        return PRICES[base]
    m = _MODEL_RE.match(base)
    if not m:
        return _DEFAULT_PRICE
    fam = m.group(1)
    best = None
    for k in PRICES:
        km = _MODEL_RE.match(k)
        if km and km.group(1) == fam and (best is None or _ver(km.group(2)) > _ver(best[0])):
            best = (km.group(2), k)
    return PRICES[best[1]] if best else _DEFAULT_PRICE

def calc_cost(r):
    p = price_for(r.get("model", ""))
    if _MODEL_DATE_SUFFIX_RE.sub("", r.get("model", "")) == "claude-haiku-5-5" and             r["input"] + r["cache_read"] + r.get("cache_write", 0) > _HAIKU_55_LONG_AT:
        p = _HAIKU_55_LONG
    M = 1_000_000
    cache_1h = r.get("cache_1h", 0)
    cache_5m = r.get("cache_5m", 0)
    if cache_1h or cache_5m:
        cache_write_cost = (cache_1h * p.get("cache_write_1h", p["cache_write"] * 2)
                             + cache_5m * p["cache_write"]) / M
    else:
        cache_write_cost = r.get("cache_write", 0) * p["cache_write"] / M
    return (
        r["input"]      * p["input"]  / M +
        cache_write_cost +
        r["cache_read"] * p["cache_read"] / M +
        r["output"]     * p["output"] / M
    )

def _load_turn_cost_baseline():
    if _TURN_COST_BASELINE_FILE.exists():
        try:
            return json.loads(_TURN_COST_BASELINE_FILE.read_text())
        except Exception:
            pass
    return {}

def _save_turn_cost_baseline(baseline):
    try:
        _TURN_COST_BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TURN_COST_BASELINE_FILE.write_text(json.dumps(baseline))
    except Exception:
        pass

def _update_turn_cost_baseline(model, cost):
    key = _entry_fee_key(model)
    baseline = _load_turn_cost_baseline()
    samples = baseline.get(key, [])
    samples.append(cost)
    baseline[key] = samples[-_TURN_COST_BASELINE_MAX_SAMPLES:]
    _save_turn_cost_baseline(baseline)

def _turn_cost_baseline_median(model):
    samples = _load_turn_cost_baseline().get(_entry_fee_key(model), [])
    if len(samples) < 3:
        return None
    return statistics.median(samples)

def _turn_cost_alert(calls, cost):
    r = calls[-1]
    model = r.get("model", "")
    prior_costs = [calc_cost(x) for x in calls[:-1] if x.get("model") == model]
    prior_costs = [c for c in prior_costs if c > 0]

    if cost > 0:
        _update_turn_cost_baseline(model, cost)

    if cost < _TURN_COST_ALERT_FLOOR:
        return None

    if len(prior_costs) >= 3:
        baseline = statistics.median(prior_costs)
        source = "this session's"
    else:
        baseline = _turn_cost_baseline_median(model)
        source = "cross-session"
        if baseline is None:
            return None

    if baseline <= 0:
        return None
    ratio = cost / baseline
    if ratio >= _TURN_COST_ALERT_MULT:
        return f"⚠️ This turn cost {ratio:.1f}x the {source} {model} median (median ${baseline:.4f}; use --last to locate the turn)"
    return None

def _entry_fee_now():
    path = find_session()
    calls = parse_calls(path)
    if not calls:
        return None, None
    first = calls[0]
    fee = first["input"] + first["cache_write"]
    return first["model"], fee

def _current_account_id():
    try:
        oauth = json.loads((_CLAUDE_JSON).read_text()).get("oauthAccount", {})
        return oauth.get("organizationUuid") or oauth.get("accountUuid") or "unknown"
    except Exception:
        return "unknown"

def _entry_fee_key(model):
    return f"{_current_account_id()}:{model}"

def _load_entry_fee_baseline():
    if _ENTRY_FEE_FILE.exists():
        try:
            return json.loads(_ENTRY_FEE_FILE.read_text())
        except Exception:
            pass
    return {}

def entry_fee_check():
    model, fee = _entry_fee_now()
    if model is None:
        return
    key = _entry_fee_key(model)
    baseline = _load_entry_fee_baseline()
    base = baseline.get(key)
    if base is None:
        baseline[key] = fee
        _ENTRY_FEE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _ENTRY_FEE_FILE.write_text(json.dumps(baseline, indent=2))
        return
    if base <= 0:
        return
    pct = (fee - base) / base * 100
    if pct >= _ENTRY_FEE_ALERT_PCT:
        print(f"💡 Entry fee rose from {fmt_k(base)} to {fmt_k(fee)} (+{pct:.0f}%), "
              f"possibly a newly installed skill/MCP. Accept the new baseline? ({model})")

def entry_fee_accept():
    model, fee = _entry_fee_now()
    if model is None:
        print("The current session has no calls yet; cannot set a baseline")
        return
    baseline = _load_entry_fee_baseline()
    baseline[_entry_fee_key(model)] = fee
    _ENTRY_FEE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ENTRY_FEE_FILE.write_text(json.dumps(baseline, indent=2))
    print(f"✅ New baseline accepted: {model} = {fmt_k(fee)}")

def fmt_k(n):
    return f"{n/1000:.1f}K" if n >= 1000 else str(n)

def fmt_kc(n, cost):
    return f"{fmt_k(n)}(${cost:.2f})"

def pipe_to_pager(text):
    pager = os.environ.get("PAGER", "less")
    try:
        proc = subprocess.Popen([pager, "-R"], stdin=subprocess.PIPE)
        proc.communicate(text.encode())
    except FileNotFoundError:
        print(text, end="")

def paginate(lines, page_size):
    total = len(lines)
    for i, line in enumerate(lines):
        print(line)
        if (i + 1) % page_size == 0 and i + 1 < total:
            try:
                ans = input(f"\n── {i+1}/{total} ── Enter to continue / q to quit: ")
                if ans.strip().lower() == "q":
                    break
            except (EOFError, KeyboardInterrupt):
                print()
                break

_HABIT_LONG_ANSWER_CHARS = 1200
_HABIT_LONG_ANSWER_STEPS = 5
_HABIT_SHORT_QUESTION_CHARS = 60
_HABIT_FAT_CTX_TOKENS = 100_000
_HABIT_TINY_PROMPT_CHARS = 30
_HABIT_FAT_SESSION_END = 80_000
_HABIT_MAX_EXAMPLES = 2
_HABIT_POST_COMPACT_WINDOW_SEC = 1800
_HABIT_MIN_POST_COMPACT_CORRECTIONS = 2
_HABIT_SLOW_SCAN_SEC = 8
_HABIT_EXPLORE_TOOLS = {"Read", "Grep", "Glob"}
_HABIT_EXPLORE_MIN_CALLS = 2

def _detect_explore_before_delegate(tool_names):
    explore = sum(1 for n in tool_names if n in _HABIT_EXPLORE_TOOLS)
    return explore >= _HABIT_EXPLORE_MIN_CALLS and "Task" in tool_names

# Chinese user-phrasing triggers (question/correction detection) kept as unicode escapes so they still match.
_QUESTION_RE = re.compile(r"[?\uff1f]|\u55ce|\u662f\u4e0d\u662f|\u4ec0\u9ebc\u610f\u601d|\u54ea\u4e00?\u53f0|\u54ea\u500b|which|what do you mean", re.I)
_STEP_LINE_RE = re.compile(r"^\s*\d+[\.\)\u3001]\s", re.M)
_CORRECTION_RE = re.compile(
    r"^(\u4e0d\u8981|\u4e0d\u7528|\u5225|\u4e0d\u662f|\u505c|\u4e0d\u5c0d|\u932f\u4e86|\u6211\u8aaa\u904e|\u53c8\u4f86|\u518d\u8aaa\u4e00\u6b21|don'?t|stop|no[,\uff0c]|wrong|not that)", re.I)

def _iso_ts(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return None

def _session_turns(path):
    entries = []
    seen = set()
    compact_ts = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("type") == "system" and e.get("subtype") == "compact_boundary":
                ts = e.get("timestamp")
                if ts:
                    compact_ts.append(ts)
            uid = e.get("uuid") or e.get("requestId")
            if uid and uid in seen:
                continue
            if uid:
                seen.add(uid)
            entries.append(e)
    entries.sort(key=lambda e: e.get("timestamp", ""))
    compact_ts.sort()

    turns = []
    seen_msg = set()
    cur = None
    for e in entries:
        t = e.get("type")
        if e.get("isSidechain"):
            continue
        if t == "user":
            content = e.get("message", {}).get("content", "")
            if isinstance(content, list) and all(
                isinstance(b, dict) and b.get("type") != "text" for b in content
            ):
                continue
            text = get_text(content).strip()
            if not text or text.startswith("<"):
                continue
            if cur:
                turns.append(cur)
            cur = {"user": text, "asst": "", "cache_read": 0, "cost": 0.0,
                   "reread": 0.0, "reread_ctx": 0, "ts": e.get("timestamp", ""), "tools": []}
        elif t == "assistant" and cur is not None:
            msg = e.get("message", {})
            content = msg.get("content", [])
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "text":
                        cur["asst"] += b.get("text", "")
                    elif isinstance(b, dict) and b.get("type") == "tool_use":
                        cur["tools"].append(b.get("name", ""))
            usage = msg.get("usage")
            mid = msg.get("id")
            if mid and mid in seen_msg:
                usage = None
            elif mid:
                seen_msg.add(mid)
            if usage:
                r = {
                    "model": msg.get("model", ""),
                    "input": usage.get("input_tokens", 0),
                    "cache_read": usage.get("cache_read_input_tokens", 0),
                    "cache_write": usage.get("cache_creation_input_tokens", 0),
                    "output": usage.get("output_tokens", 0),
                }
                cur["cache_read"] = r["cache_read"]
                if cur["cost"] == 0.0:
                    p = price_for(r["model"])
                    ctx = r["input"] + r["cache_read"] + r["cache_write"]
                    cur["reread"] = (r["cache_read"] * p["cache_read"]
                                     + r["cache_write"] * p["cache_write"]
                                     + r["input"] * p["input"]) / 1e6
                    cur["reread_ctx"] = ctx
                cur["cost"] += calc_cost(r)
    if cur:
        turns.append(cur)
    return turns, compact_ts

def _snip(s, n=90):
    s = s.replace("\n", " ").strip()
    return s if len(s) <= n else s[:n - 1] + "…"

def nap_timing_report(days=None):
    since_ts = None
    if days is not None:
        since_ts = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    calls = parse_all_sessions(since_date=since_ts)
    calls = [r for r in calls if not r.get("is_subagent") and r.get("entrypoint") == "cli"]
    if not calls:
        print("Not enough interaction data to analyze")
        return

    first_cw = {}
    later_cw = {}
    seen_first = set()
    for r in calls:
        model = r.get("model", "")
        if not model or model == "<synthetic>":
            continue
        cw = r["cache_write"]
        if cw <= 0:
            continue
        key = (r["session"], model)
        if key not in seen_first:
            seen_first.add(key)
            first_cw.setdefault(model, []).append(cw)
        else:
            later_cw.setdefault(model, []).append(cw)

    rows = []
    for model in first_cw:
        F_list = first_cw.get(model, [])
        C_list = later_cw.get(model, [])
        if len(F_list) < 3 or len(C_list) < 10:
            continue
        F = statistics.median(F_list)
        C = statistics.median(C_list)
        p = price_for(model)
        if C <= 0 or p["cache_read"] <= 0:
            continue
        m_star = math.sqrt(2 * p["cache_write"] * F / (p["cache_read"] * C))
        rows.append((model, len(F_list), F, C, m_star, m_star * C))

    if not rows:
        print("Too few samples for every model (need at least 3 sessions and 10 turns on the same model), "
              "re-run after more interaction history accumulates")
        return

    span = f"last {days} days" if days else "all history"
    print(f"\n🧭 Nap timing suggestion ({span}, human interaction only; subagent/automated traffic excluded)\n")
    print(f"{'model':<26}{'sessions':>9}{'F fixed':>11}{'C per turn':>11}{'sweet spot':>11}{'new tokens':>11}")
    for model, n, F, C, m_star, tok in sorted(rows, key=lambda x: -x[1]):
        print(f"{model:<26}{n:>9}{F:>11,.0f}{C:>11,.0f}{m_star:>8.0f} turns{tok:>10,.0f}")
    top = max(rows, key=lambda x: x[1])
    sug = max(50000, int(round(top[5] / 10000.0)) * 10000)
    print(f"\nSuggested nudge_growth_tokens: {sug} (new tokens at the sweet spot of {top[0]}, floor 50000); set it in oct-toolkit.json")
    print("\nSweet spot = the reset point where fixed and growth costs balance; not a hard limit. When there is a natural stopping point, "
          "prefer it; this is only a reference line for roughly where a long, unwrapped session starts to really burn money.")

def habits_report(days=7):
    _scan_start = time.monotonic()
    projects = _CLAUDE_DIR / "projects"
    cutoff = datetime.now().timestamp() - days * 86400
    files = [f for f in projects.rglob("*.jsonl") if f.stat().st_mtime >= cutoff]

    summaries = _CLAUDE_DIR / "summaries"
    nap_times = []
    if summaries.exists():
        for f in list(summaries.glob("*.md")) + list((summaries / "archive").glob("*.md")):
            nap_times.append(f.stat().st_mtime)

    wall_then_q = []
    fat_chatter = []
    corrections = []
    fat_no_nap = []
    post_compact_corr = []
    explore_before_delegate = []
    now = datetime.now().timestamp()

    for f in files:
        sid = f.stem[:8]
        turns, compact_ts_raw = _session_turns(f)
        if not turns:
            continue
        compact_ts = [t for t in (_iso_ts(c) for c in compact_ts_raw) if t is not None]
        for i, t in enumerate(turns):
            asst = t["asst"]
            is_wall = (len(asst) >= _HABIT_LONG_ANSWER_CHARS
                       or len(_STEP_LINE_RE.findall(asst)) >= _HABIT_LONG_ANSWER_STEPS)
            if is_wall and i + 1 < len(turns):
                nxt = turns[i + 1]
                if len(nxt["user"]) <= _HABIT_SHORT_QUESTION_CHARS and _QUESTION_RE.search(nxt["user"]):
                    wall_then_q.append((nxt["reread"], sid, nxt["ts"], nxt["user"]))
            if t["reread_ctx"] >= _HABIT_FAT_CTX_TOKENS and len(t["user"]) <= _HABIT_TINY_PROMPT_CHARS:
                fat_chatter.append((t["reread"], sid, t["ts"], t["user"], t["reread_ctx"]))
            if _CORRECTION_RE.match(t["user"]):
                corrections.append((sid, t["ts"], t["user"]))
                t_ts = _iso_ts(t["ts"])
                if t_ts is not None and compact_ts:
                    prior = [c for c in compact_ts if c <= t_ts]
                    if prior and t_ts - max(prior) <= _HABIT_POST_COMPACT_WINDOW_SEC:
                        post_compact_corr.append((sid, t["ts"], t["user"], len(compact_ts)))
            if _detect_explore_before_delegate(t.get("tools", [])):
                explore_calls = sum(1 for n in t["tools"] if n in _HABIT_EXPLORE_TOOLS)
                explore_before_delegate.append((sid, t["ts"], t["user"], explore_calls))

        last = turns[-1]
        end = f.stat().st_mtime
        if last["cache_read"] >= _HABIT_FAT_SESSION_END and now - end > 3600:
            if not any(abs(nt - end) <= 900 for nt in nap_times):
                fat_no_nap.append((sid, last["cache_read"], end))

    out = []
    out.append(f"🩺 oct-checkup habits  |  last {days} days, {len(files)} sessions\n")
    fired = 0

    def ex_line(sid, ts, text):
        return f"      · {sid} {ts[5:16].replace('T', ' ')}  \"{_snip(text)}\""

    if wall_then_q:
        fired += 1
        cost = sum(c for c, *_ in wall_then_q)
        out.append(f"1. Short follow-up right after a long answer  ×{len(wall_then_q)}  re-reading context alone ≈${cost:.2f}")
        out.append("   Claude dumped a wall of text (or 5+ steps) and you had to ask halfway. Every extra question re-reads the whole conversation.")
        for c, sid, ts, txt in sorted(wall_then_q, reverse=True)[:_HABIT_MAX_EXAMPLES]:
            out.append(ex_line(sid, ts, txt))
        out.append("   Suggested rule: for operational procedures give one step at a time, name the target, wait for a report before the next step; write long conclusions to a file and share only the path.\n")

    if fat_chatter:
        fired += 1
        cost = sum(c for c, *_ in fat_chatter)
        out.append(f"2. Short back-and-forth in a fat conversation  ×{len(fat_chatter)}  re-reading context alone ≈${cost:.2f}")
        out.append(f"   Once context exceeds {_HABIT_FAT_CTX_TOKENS // 1000}K, even replying \"ok\" pays for a full re-read.")
        for c, sid, ts, txt, ctx in sorted(fat_chatter, reverse=True)[:_HABIT_MAX_EXAMPLES]:
            out.append(ex_line(sid, ts, txt) + f"  ctx {fmt_k(ctx)} → ${c:.2f} just to read this")
        out.append("   Suggested habit: past half ctx, /oct-nap then /clear and continue from the note; do not drag a fat conversation along.\n")

    if len(corrections) >= 3:
        fired += 1
        by_sess = {}
        for sid, ts, txt in corrections:
            by_sess.setdefault(sid, []).append((ts, txt))
        out.append(f"3. Repeatedly correcting Claude  ×{len(corrections)}, across {len(by_sess)} sessions")
        out.append("   A correction said a second time should be a long-term memory, not a one-off sentence.")
        for sid, ts, txt in corrections[-_HABIT_MAX_EXAMPLES:]:
            out.append(ex_line(sid, ts, txt))
        out.append("   Suggestion: save the repeated correction as a feedback memory (rule + why + when to apply).\n")

    if fat_no_nap:
        fired += 1
        out.append(f"4. Fat session ended without a note  ×{len(fat_no_nap)}")
        out.append(f"   Context was still {_HABIT_FAT_SESSION_END // 1000}K+ at the end; a later --resume recomputes all of it cold.")
        for sid, cr, end in sorted(fat_no_nap, key=lambda x: -x[1])[:_HABIT_MAX_EXAMPLES]:
            out.append(f"      · {sid}  ctx {fmt_k(cr)}  {datetime.fromtimestamp(end).strftime('%m-%d %H:%M')}")
        out.append("   Suggested habit: /oct-nap before stopping; next time /oct-wake reads only a 1-2k note.\n")

    if len(post_compact_corr) >= _HABIT_MIN_POST_COMPACT_CORRECTIONS:
        fired += 1
        by_sess = {}
        for sid, ts, txt, ccount in post_compact_corr:
            by_sess.setdefault(sid, []).append((ts, txt, ccount))
        out.append(f"5. Corrected again right after compaction  ×{len(post_compact_corr)}, across {len(by_sess)} sessions")
        out.append("   Shortly after an auto-compact you had to repeat a similar correction, as if the rule only lived in the conversation and "
                    "was diluted by compaction rather than truly remembered. (This is a timing-coincidence heuristic and does not guarantee the two are related; "
                    "the more compactions that day, the likelier a coincidence, so check the examples and discount sessions with many compactions.)")
        for sid, ts, txt, ccount in post_compact_corr[-_HABIT_MAX_EXAMPLES:]:
            out.append(ex_line(sid, ts, txt) + f"  (this session compacted {ccount} times that day)")
        out.append("   Suggestion: move this kind of rule into CLAUDE.md (global or project-level) instead of relying on the conversation to survive compaction.\n")

    if explore_before_delegate:
        fired += 1
        out.append(f"6. Exploring yourself before delegating  ×{len(explore_before_delegate)}")
        out.append("   Within one turn you Read/Grep/Glob'd first and then still dispatched a subagent; the findings mostly did not make it into the prompt, "
                    "so the subagent re-explores, or what you just read was wasted.")
        for sid, ts, txt, n in sorted(explore_before_delegate, key=lambda x: -x[3])[:_HABIT_MAX_EXAMPLES]:
            out.append(ex_line(sid, ts, txt) + f"  ({n} exploration calls + at least 1 delegate in the same turn)")
        out.append("   Suggested habit: if you will delegate, dispatch straight away without exploring first; if you are already partway through exploring, "
                    "write what you found into the prompt before dispatching so the subagent does not start from zero.\n")

    scan_secs = time.monotonic() - _scan_start
    if scan_secs >= _HABIT_SLOW_SCAN_SEC:
        out.append(f"⏱️ This scan itself took {scan_secs:.1f}s ({len(files)} sessions, {days} days)"
                    " - this tool should be a light local scan, so that is slow.")
        out.append("   If this is typical, please report it: https://github.com/sunososobro-hub/claude-octopus/issues"
                    " (just include this number; no conversation content needed)\n")

    if fired == 0:
        out.append(f"✅ No obvious waste patterns in the last {days} days.")
    else:
        out.append("Which of these should be saved as long-term memory? (e.g. \"1 3\" / \"all\" / \"none\")")
    print("\n".join(out))

_OCT_DIR = _CLAUDE_DIR / "oct-toolkit"
_BASELINE_FILE = _OCT_DIR / "baseline.json"
_SAVINGS_FILE = _OCT_DIR / "savings.json"
_READ_BLOCKS_FILE = _OCT_DIR / "read-blocks.jsonl"
_NAP_EVENTS_FILE = _OCT_DIR / "nap-events.jsonl"
_SAVINGS_LOCK = _OCT_DIR / "savings.lock"
_BASE_DAYS = 30
_BASE_MAX_FILES = 400
_BASE_BUDGET_S = 120
_BASE_MIN_TURNS = 10
_SAVINGS_TTL_S = 300
_SAVINGS_SHORT_S = 5 * 3600
_BADGE_MIN_TURNS_5H = 10
_BADGE_MIN_USD_5H = 0.05
_READ_FOLLOW_TURNS = 10
_READ_MAX_BYTES = 100000

def _iso_utc(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

def _norm_model(m):
    m = _MODEL_DATE_SUFFIX_RE.sub("", m or "")
    return "" if (not m or m.startswith("<")) else m

def _read_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def _write_json(p, d):
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(d), encoding="utf-8")
        os.replace(tmp, p)
    except Exception:
        pass

def _spawn_bg(args):
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x08000000 | 0x00000200
    else:
        kw["start_new_session"] = True
    try:
        subprocess.Popen([sys.executable, os.path.abspath(__file__)] + args, **kw)
    except Exception:
        pass

def _file_msgs(path):
    msgs = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"assistant"' not in line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                m = e.get("message") or {}
                u = m.get("usage")
                if e.get("type") != "assistant" or not u:
                    continue
                k = m.get("id") or e.get("uuid") or str(len(msgs))
                cur = msgs.get(k)
                if cur is None:
                    cur = msgs[k] = {"reads": []}
                cc = u.get("cache_creation") or {}
                cur.update({
                    "ts": e.get("timestamp", ""),
                    "model": _norm_model(m.get("model")),
                    "call": {"model": m.get("model", ""), "input": u.get("input_tokens", 0),
                             "cache_read": u.get("cache_read_input_tokens", 0),
                             "cache_write": u.get("cache_creation_input_tokens", 0),
                             "output": u.get("output_tokens", 0),
                             "cache_1h": cc.get("ephemeral_1h_input_tokens", 0),
                             "cache_5m": cc.get("ephemeral_5m_input_tokens", 0)},
                })
                if isinstance(m.get("content"), list):
                    for b in m["content"]:
                        if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Read":
                            fp = (b.get("input") or {}).get("file_path")
                            if fp:
                                cur["reads"].append(fp)
    except OSError:
        return []
    return [m for m in msgs.values() if "ts" in m]

def _scan(files, t0, t1, deadline=None):
    agg = {}
    for f in files:
        if deadline and time.time() > deadline:
            break
        seen = set()
        per = {}
        for m in _file_msgs(f):
            if not m["model"] or not (t0 <= m["ts"] < t1):
                continue
            a = agg.setdefault(m["model"], {"turns": 0, "cost": 0.0, "ctx": 0, "sess": [], "reads": 0, "rereads": 0})
            c = m["call"]
            a["turns"] += 1
            a["cost"] += calc_cost(c)
            a["ctx"] += c["input"] + c["cache_read"] + c["cache_write"]
            per[m["model"]] = per.get(m["model"], 0) + 1
            for fp in m["reads"]:
                a["reads"] += 1
                if fp in seen:
                    a["rereads"] += 1
                seen.add(fp)
        if f.parent.name != "subagents":
            for mod, n in per.items():
                agg[mod]["sess"].append(n)
    out = {}
    for mod, a in agg.items():
        n = a["turns"]
        out[mod] = {"turns": n, "turn_cost": a["cost"] / n, "turn_ctx": a["ctx"] / n,
                    "sess_len": (sum(a["sess"]) / len(a["sess"])) if a["sess"] else 0,
                    "reread": (a["rereads"] / a["reads"]) if a["reads"] else 0}
    return out

def _jsonl_files(since):
    out = []
    try:
        for f in (_CLAUDE_DIR / "projects").rglob("*.jsonl"):
            try:
                mt = f.stat().st_mtime
            except OSError:
                continue
            if mt >= since:
                out.append((mt, f))
    except OSError:
        pass
    return [f for _, f in sorted(out, key=lambda x: x[0], reverse=True)]

def baseline_compute():
    b = _read_json(_BASELINE_FILE)
    if b and b.get("status") == "done":
        return
    install = (b or {}).get("install_ts") or time.time()
    files = _jsonl_files(install - _BASE_DAYS * 86400)[:_BASE_MAX_FILES]
    t0 = time.time()
    models = _scan(files, "", _iso_utc(install), t0 + _BASE_BUDGET_S)
    usable = {m: v for m, v in models.items() if v["turns"] >= _BASE_MIN_TURNS}
    _write_json(_BASELINE_FILE, {"status": "done", "install_ts": install, "computed_at": time.time(),
                                 "mode": "history" if usable else "none", "files": len(files),
                                 "secs": round(time.time() - t0, 1), "models": usable})

def _log_nap_event(h, model, ctx, ck):
    try:
        _OCT_DIR.mkdir(parents=True, exist_ok=True)
        if _NAP_EVENTS_FILE.exists() and ('"h": "%s"' % h) in _NAP_EVENTS_FILE.read_text(encoding="utf-8"):
            return
        with open(_NAP_EVENTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "h": h, "model": _norm_model(model),
                                "ctx": ctx, "ck": ck, "slug": re.sub(r"[^A-Za-z0-9]", "-", os.getcwd())}) + "\n")
    except Exception:
        pass

def _nap_cf_saving(events, week_start, base=None, windows=None):
    total = 0.0
    base = base or {}
    for i, ev in enumerate(events):
        nxt = min([x["ts"] for x in events[i + 1:] if x["slug"] == ev["slug"]] or [float("inf")])
        lo = _iso_utc(max(ev["ts"], week_start))
        hi = _iso_utc(nxt) if nxt != float("inf") else "9"
        evt = _iso_utc(ev["ts"])
        n, actual = 0, 0.0
        for f in (_CLAUDE_DIR / "projects" / ev["slug"]).glob("*.jsonl"):
            ms = _file_msgs(f)
            if not ms or min(m["ts"] for m in ms) <= evt:
                continue
            for m in ms:
                if lo <= m["ts"] < hi:
                    n += 1
                    actual += calc_cost(dict(m["call"], output=0))
        cap = (base.get(ev["model"]) or {}).get("sess_len") or 0
        if cap and n > cap:
            actual *= cap / n
            n = cap
        cf = n * ev["ctx"] * price_for(ev["model"])["cache_read"] / 1_000_000
        sv = max(0.0, cf - actual)
        if sv > 0 and windows is not None:
            windows.append((max(ev["ts"], week_start), nxt))
        total += sv
    return total

def _savings_window(start, now, b, events_all, block_rows):
    """Estimated savings and actual spend inside [start, now]. Counterfactual: spend without oct = actual + saved."""
    agg = _scan(_jsonl_files(start), _iso_utc(start), _iso_utc(now + 86400))
    base = b.get("models", {})
    wins = []
    nap = _nap_cf_saving([e for e in events_all if e["ts"] >= start - 7 * 86400], start, base, wins)
    blocks, nbytes = 0, 0
    for r in block_rows:
        if r["t"] >= start and not any(lo <= r["t"] < hi for lo, hi in wins):
            blocks += 1
            nbytes += min(r["b"], _READ_MAX_BYTES)
    dom = max(agg, key=lambda m: agg[m]["turns"]) if agg else ""
    p = price_for(dom)
    read_cost = (nbytes / 4) * (p["cache_write"] + _READ_FOLLOW_TURNS * p["cache_read"]) / 1_000_000
    return {"nap": round(nap, 4), "read": round(read_cost, 4), "blocks": blocks,
            "turns": sum(v["turns"] for v in agg.values()),
            "actual": round(sum(v["turns"] * v["turn_cost"] for v in agg.values()), 4),
            "saved": round(max(0.0, nap + read_cost), 4)}

def savings_refresh(if_stale=False):
    b = _read_json(_BASELINE_FILE)
    if not b or b.get("status") != "done":
        return
    now = time.time()
    if if_stale:
        cur = _read_json(_SAVINGS_FILE)
        if cur and now - cur.get("computed_at", 0) < _SAVINGS_TTL_S:
            return
        try:
            if _SAVINGS_LOCK.exists() and now - _SAVINGS_LOCK.stat().st_mtime < 300:
                return
            _SAVINGS_LOCK.write_text(str(now))
        except OSError:
            return
    start = max(b.get("install_ts", now), now - 7 * 86400)
    start5 = max(b.get("install_ts", now), now - _SAVINGS_SHORT_S)
    events = []
    try:
        for line in _NAP_EVENTS_FILE.read_text(encoding="utf-8").splitlines():
            events.append(json.loads(line))
    except Exception:
        pass
    rows, lines = [], []
    try:
        lines = _READ_BLOCKS_FILE.read_text(encoding="utf-8").splitlines()
        for line in lines:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
        if len(lines) > 3000:
            _READ_BLOCKS_FILE.write_text(chr(10).join(lines[-1500:]) + chr(10), encoding="utf-8")
    except Exception:
        pass
    w7 = _savings_window(start, now, b, [e for e in events if e["ts"] >= start], rows)
    w5 = _savings_window(start5, now, b, [e for e in events if e["ts"] >= start], rows)
    _write_json(_SAVINGS_FILE, {"computed_at": now, "since": start, "mode": b.get("mode"),
                                "nap": w7["nap"], "read": w7["read"], "blocks": w7["blocks"],
                                "turns": w7["turns"], "total": w7["saved"], "w7": w7, "w5": w5})
    cur = _read_json(_SAVINGS_FILE)
    if cur and cur["total"] < _WHY_MIN_USD:
        try:
            cur["why"] = savings_why(cur)
        except Exception:
            cur["why"] = None
        _write_json(_SAVINGS_FILE, cur)
    try:
        ln = _NUDGES_FILE.read_text(encoding="utf-8").splitlines()
        if len(ln) > 1000:
            _NUDGES_FILE.write_text("\n".join(ln[-500:]) + "\n", encoding="utf-8")
    except OSError:
        pass

_NUDGES_FILE = _OCT_DIR / "nudges.jsonl"
_CLEARS_FILE = _OCT_DIR / "clears.jsonl"
_WHY_MIN_TURNS = 50
_WHY_MIN_USD = 0.01
_NUDGE_GROWTH_DEFAULT = 80000

def _cfg_val(key, default):
    try:
        v = json.loads((_CLAUDE_DIR / "oct-toolkit.json").read_text(encoding="utf-8")).get(key, default)
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else default
    except Exception:
        return default

def _count_since(p, start):
    try:
        return sum(1 for l in p.read_text(encoding="utf-8").splitlines() if json.loads(l).get("ts", 0) >= start)
    except Exception:
        return 0

def _week_sessions(start, model):
    t0 = _iso_utc(start)
    out = []
    for f in _jsonl_files(start):
        if f.parent.name == "subagents":
            continue
        ctxs = []
        for m in _file_msgs(f):
            if m["model"] == model and m["ts"] >= t0:
                c = m["call"]
                ctxs.append(c["input"] + c["cache_read"] + c["cache_write"])
        if ctxs:
            out.append(ctxs)
    return out

def _round5k(x):
    return int(round(x / 5000.0)) * 5000

def savings_why(d=None, full=False):
    now = time.time()
    b = _read_json(_BASELINE_FILE) or {}
    d = d or _read_json(_SAVINGS_FILE) or {}
    start = max(b.get("install_ts", now), now - 7 * 86400)
    m = {"turns": d.get("turns", 0), "total": d.get("total", 0.0), "blocks": d.get("blocks", 0)}
    ready = bool(b.get("status") == "done" and now - b.get("install_ts", now) >= 7 * 86400
                 and m["turns"] >= _WHY_MIN_TURNS and m["total"] < _WHY_MIN_USD)
    if not ready and not full:
        return None
    off = [k for k in ("nap_nudge", "auto_wake") if not _cfg_on(k)]
    nudges = _count_since(_NUDGES_FILE, start)
    naps = _count_since(_NAP_EVENTS_FILE, start)
    clears = _count_since(_CLEARS_FILE, start)
    acted = max(naps, clears)
    agg = _scan(_jsonl_files(start), _iso_utc(start), _iso_utc(now + 86400))
    dom = max(agg, key=lambda k: agg[k]["turns"]) if agg else ""
    sess = _week_sessions(start, dom) if dom else []
    thr = _cfg_val("nudge_growth_tokens", _NUDGE_GROWTH_DEFAULT)
    growth = [max(s) - s[0] for s in sess]
    gmax = max(growth) if growth else 0
    reach = sum(1 for g in growth if g >= thr)
    bm = (b.get("models") or {}).get(dom) or {}
    cur = agg.get(dom) or {}
    why = []
    if off:
        why.append(("e", "estimated savings this week are about $0 because %s is turned off in oct-toolkit.json. "
                    "Set it to true to turn it back on." % " and ".join(off)))
    if nudges >= 3 and acted * 3 < nudges:
        why.append(("a", "estimated savings this week are about $0: the nap reminder appeared %d times but only %d nap/clear followed. "
                    "When it appears next, run /clear (the checkpoint resumes automatically)." % (nudges, acted)))
    if bm.get("sess_len") and bm.get("turn_ctx") and cur and cur["sess_len"] <= bm["sess_len"] * 1.1 and cur["turn_ctx"] <= bm["turn_ctx"] * 1.1:
        why.append(("b", "you already keep sessions short (%.0f turns and ~%dk context per turn this week, vs %.0f turns and ~%dk before installing), "
                    "so there is little to save. The tool's value for you is automatic pick-up after /clear without dropping open items; nothing to change."
                    % (cur["sess_len"], cur["turn_ctx"] / 1000, bm["sess_len"], bm["turn_ctx"] / 1000)))
    if sess and gmax < thr and reach * 10 < len(growth):
        x = max(20000, _round5k(gmax * 0.75))
        if x < thr:
            why.append(("c", "estimated savings this week are about $0: context never grew by nudge_growth_tokens (%d); the largest session grew ~%dk. "
                        "Set nudge_growth_tokens to %d in oct-toolkit.json." % (thr, gmax / 1000, x)))
    if m["blocks"] == 0 and cur and cur["reread"] < 0.02:
        why.append(("d", "estimated savings this week are about $0: there were no duplicate file reads to block. "
                    "Nothing to fix; savings come from /oct-nap then /clear on longer sessions."))
    m.update(nudges=nudges, naps=naps, clears=clears, growth_max=gmax, thr=thr, sessions=len(growth),
             sess_len=cur.get("sess_len"), turn_ctx=cur.get("turn_ctx"), base_sess_len=bm.get("sess_len"),
             base_turn_ctx=bm.get("turn_ctx"), reread=cur.get("reread"))
    if full:
        return {"ready": ready, "m": m, "why": why}
    return {"key": why[0][0], "msg": why[0][1]} if why else None

def savings_why_print():
    savings_refresh()
    r = savings_why(full=True)
    m = r["m"]
    print("Why savings are low (past 7 days)")
    print("turns %d | est. savings $%.2f | nudges %d | naps %d | clears %d | duplicate reads blocked %d" %
          (m["turns"], m["total"], m["nudges"], m["naps"], m["clears"], m["blocks"]))
    if m["sess_len"] is not None:
        print("session length %.0f turns (before: %s) | context/turn ~%dk (before: %s) | max growth ~%dk of nudge_growth_tokens %d" %
              (m["sess_len"], "%.0f" % m["base_sess_len"] if m["base_sess_len"] else "n/a", m["turn_ctx"] / 1000,
               "~%dk" % (m["base_turn_ctx"] / 1000) if m["base_turn_ctx"] else "n/a", m["growth_max"] / 1000, m["thr"]))
    if not r["ready"]:
        print("Not enough data to call it low (needs 7+ days installed, 50+ turns, savings under $0.01); causes below are indicative only.")
    if not r["why"]:
        print("No single cause stands out.")
    for i, (k, t) in enumerate(r["why"]):
        print("%s(%s) %s" % ("Main: " if i == 0 else "Also: ", k, t))

def _fmt_usd(x):
    return f"{x:.2f}" if x < 1 else (f"{x:.1f}" if x < 100 else f"{x:.0f}")

def _pct_str(w):
    """Signed percent vs the no-oct estimate (actual + saved). Saved is never negative, so this is -N% or ~0%."""
    est = w["actual"] + w["saved"]
    if est <= 0 or w["saved"] < _WHY_MIN_USD:
        return None
    pct = 100.0 * w["saved"] / est
    return "~0%" if pct < 1 else "-%d%%" % round(pct)

def savings_badge():
    if not _cfg_on("savings_badge"):
        return ""
    d = _read_json(_SAVINGS_FILE)
    if not d:
        if _read_json(_BASELINE_FILE):
            _spawn_bg(["--savings-refresh", "--if-stale"])
        return ""
    if time.time() - d.get("computed_at", 0) >= _SAVINGS_TTL_S:
        _spawn_bg(["--savings-refresh", "--if-stale"])
    w5, w7 = d.get("w5"), d.get("w7")
    if not w7:
        return ""
    s7 = _pct_str(w7) if w7["turns"] >= _WHY_MIN_TURNS else None
    s5 = None
    if w5 and w5["turns"] >= _BADGE_MIN_TURNS_5H and w5["actual"] + w5["saved"] >= _BADGE_MIN_USD_5H:
        s5 = _pct_str(w5) or ("0%" if s7 else None)
    if s5:
        return "🐙 %s 5h" % s5 + (" (7d %s)" % s7 if s7 else "")
    if s7:
        return "🐙 %s 7d" % s7
    return ""

def main():
    args = sys.argv[1:]

    if args and args[0] == "--statusline-hook":
        statusline_hook()
        sys.exit(0)

    if args and args[0] == "--stop-hook":
        stop_hook()
        sys.exit(0)

    if args and args[0] == "--baseline":
        baseline_compute()
        sys.exit(0)

    if args and args[0] == "--savings-refresh":
        savings_refresh("--if-stale" in args)
        sys.exit(0)

    if args and args[0] == "--savings-badge":
        print(savings_badge())
        sys.exit(0)

    if args and args[0] == "--savings-why":
        savings_why_print()
        sys.exit(0)

    if args and args[0] == "--tidy-check":
        tidy_check()
        sys.exit(0)

    if args and args[0] == "--wake-state":
        wake_state()
        sys.exit(0)

    if args and args[0].startswith("--nap-savings"):
        nap_savings(args[0].partition("=")[2] or (args[1] if len(args) > 1 else ""))
        sys.exit(0)

    if args and args[0] == "--pulse-detail":
        pulse_detail()
        sys.exit(0)

    if args and args[0] == "--entry-fee-check":
        entry_fee_check()
        sys.exit(0)

    if args and args[0] == "--entry-fee-accept":
        entry_fee_accept()
        sys.exit(0)

    if args and args[0] == "--nap-timing":
        days = None
        for a in args[1:]:
            if a.startswith("--days="):
                days = int(a.split("=", 1)[1])
        nap_timing_report(days=days)
        sys.exit(0)

    if len(args) >= 4 and args[0] == "--set-price":
        model = args[1] if args[1].startswith("claude-") else f"claude-{args[1]}"
        inp, out = float(args[2]), float(args[3])
        entry = {"input": inp, "cache_write": round(inp * 1.25, 4),
                 "cache_read": round(inp * 0.10, 4), "output": out}
        data = json.loads(_PRICES_FILE.read_text()) if _PRICES_FILE.exists() else {}
        data[model] = entry
        _PRICES_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PRICES_FILE.write_text(json.dumps(data, indent=2))
        print(f"Updated {model}: input=${inp} output=${out} (prices.json)")
        sys.exit(0)

    last_n = None
    summary = False
    detail = False
    pager = False
    page_size = None
    reverse = False
    sort_cost = False
    show_n = None
    list_sessions_flag = False
    current_flag = False
    watch_flag = False
    reflect_flag = False
    habits_flag = False
    habits_days = 7
    since_date = None
    session_id = None
    watch_transcript = None
    watch_session = None
    for a in args:
        if a == "--habits":
            habits_flag = True
        elif a.startswith("--days="):
            habits_days = int(a.split("=")[1])
        elif a.startswith("--last="):
            last_n = int(a.split("=")[1])
        elif a == "--last":
            last_n = 1
        elif a == "--summary":
            summary = True
        elif a == "--detail":
            detail = True
        elif a == "--pager":
            pager = True
        elif a == "--reverse" or a == "-r":
            reverse = True
        elif a == "--sort=cost" or a == "--sort-cost":
            sort_cost = True
        elif a.startswith("--page-size=") or a.startswith("--ps="):
            page_size = int(a.split("=")[1])
        elif a.startswith("--show="):
            show_n = int(a.split("=")[1])
        elif a == "--sessions":
            list_sessions_flag = True
        elif a == "--current":
            current_flag = True
        elif a == "--watch":
            watch_flag = True
        elif a.startswith("--transcript="):
            watch_transcript = a.split("=", 1)[1]
        elif a.startswith("--session="):
            watch_session = a.split("=", 1)[1]
        elif a == "--reflect-stats":
            reflect_flag = True
        elif a.startswith("--since="):
            since_date = a.split("=", 1)[1]
        else:
            session_id = a

    if habits_flag:
        habits_report(days=habits_days)
        sys.exit(0)

    if reflect_flag:
        calls = parse_all_sessions(since_date=since_date)
        print(json.dumps(reflect_stats_compute(calls), indent=2))
        sys.exit(0)

    if watch_flag:
        if not _cfg_on("cost_line"):
            sys.exit(0)
        if watch_transcript and os.path.isfile(watch_transcript):
            path = Path(watch_transcript)
        else:
            path = find_session(watch_session or session_id)
        calls = parse_calls(path)
        if not calls:
            sys.exit(0)
        r = calls[-1]
        import hashlib
        claim = _CLAUDE_DIR / "scripts" / (".watch-" + hashlib.sha1((path.name + r["timestamp"]).encode()).hexdigest()[:16])
        try:
            claim.parent.mkdir(parents=True, exist_ok=True)
            for old in claim.parent.glob(".watch-*"):
                if old != claim:
                    old.unlink(missing_ok=True)
            os.close(os.open(str(claim), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            sys.exit(0)
        except OSError:
            pass
        main_calls, sub_calls = turn_calls(path)
        if not main_calls:
            sys.exit(0)
        t = sum_calls(main_calls)
        cost = calc_cost(r)
        in_c  = fmt_kc(t['input'],       t['c_input'])
        cr_c  = fmt_kc(t['cache_read'],  t['c_cache_read'])
        cw_c  = fmt_kc(t['cache_write'], t['c_cache_write'])
        out_c = fmt_kc(t['output'],      t['c_output'])
        line = f"💰 In:{in_c}  CR:{cr_c}  CW:{cw_c}  Out:{out_c}  =${t['cost']:.4f}"
        if sub_calls:
            st = sum_calls(sub_calls)
            line += (f"\n   ↳ subagents ({len(sub_calls)} calls): In:{fmt_kc(st['input'], st['c_input'])}  "
                     f"CR:{fmt_kc(st['cache_read'], st['c_cache_read'])}  CW:{fmt_kc(st['cache_write'], st['c_cache_write'])}  "
                     f"Out:{fmt_kc(st['output'], st['c_output'])}  =${st['cost']:.4f}")
        alert = _turn_cost_alert(calls, cost)
        if alert:
            print(f"\033[31m{line}\033[0m")
            print(f"\033[31m{alert}\033[0m")
        else:
            print(line)
        sys.exit(0)

    if list_sessions_flag:
        list_sessions(sort_by_cost=sort_cost, last_n=last_n if last_n is not None else 20)
        sys.exit(0)

    no_session_arg = not session_id
    if current_flag:
        path = find_session()
        calls = parse_calls(path)
        session_id = path.stem[:8]
        no_session_arg = False
    elif session_id:
        path = find_session(session_id)
        calls = parse_calls(path)
        for r in calls:
            r["session"] = path.stem[:8]
    else:
        path = find_session()
        calls = parse_all_sessions(since_date=since_date)

    if not calls:
        print("No token data found in session")
        sys.exit(0)

    total_calls = len(calls)
    if last_n is not None:
        calls = calls[-last_n:]
    if sort_cost:
        calls = sorted(calls, key=calc_cost, reverse=True)
    elif reverse:
        calls = list(reversed(calls))

    for i, r in enumerate(calls, 1):
        r["_idx"] = i

    if show_n is not None:
        if 1 <= show_n <= len(calls):
            show_call(path, calls[show_n - 1])
        else:
            print(f"#{show_n} out of range (1–{len(calls)})")
        sys.exit(0)

    session_name = path.stem[:8]
    date = calls[0]["timestamp"][:10] if calls[0]["timestamp"] else "?"
    shown = len(calls)
    if last_n and total_calls > last_n:
        label = f"latest {shown} of {total_calls}"
    elif last_n:
        label = f"latest {shown}"
    else:
        label = f"{shown} API calls"

    total = {k: 0 for k in ("input","cache_read","cache_write","output","web_search","web_fetch")}
    total_costs = {"input": 0.0, "cache_read": 0.0, "cache_write": 0.0, "output": 0.0}
    for r in calls:
        for k in total:
            total[k] += r[k]
        p = price_for(r.get("model", ""))
        M = 1_000_000
        total_costs["input"]       += r["input"]      * p["input"]      / M
        total_costs["cache_read"]  += r["cache_read"] * p["cache_read"] / M
        total_costs["output"]      += r["output"]     * p["output"]     / M
        total_costs["cache_write"] += (calc_cost(r) - r["input"] * p["input"] / M
                                        - r["cache_read"] * p["cache_read"] / M
                                        - r["output"] * p["output"] / M)

    total_cost = sum(total_costs.values())

    buf = io.StringIO() if (pager or page_size) else None
    if buf:
        sys.stdout = buf

    print(f"\n📊 oct-checkup  |  {label}\n")

    if summary:
        cache_1h_total = sum(r["cache_1h"] for r in calls)
        cache_5m_total = sum(r["cache_5m"] for r in calls)
        models = sorted(set(r["model"] for r in calls if r["model"]))
        tiers  = sorted(set(r["tier"]  for r in calls if r["tier"]))
        speeds = sorted(set(r["speed"] for r in calls if r["speed"]))
        geos   = sorted(set(r["geo"]   for r in calls if r["geo"]))
        print(f"  model:  {', '.join(models) or 'n/a'}")
        print(f"  tier:   {', '.join(tiers)  or 'n/a'}")
        print(f"  speed:  {', '.join(speeds) or 'n/a'}")
        print(f"  geo:    {', '.join(geos)   or 'n/a'}")
        print()
        M = 1_000_000
        rows = [
            ("input",          total["input"],       total["input"]       * _DEFAULT_PRICE["input"]       / M, _DEFAULT_PRICE["input"]),
            ("cache_read",     total["cache_read"],  total["cache_read"]  * _DEFAULT_PRICE["cache_read"]  / M, _DEFAULT_PRICE["cache_read"]),
            ("cache_write",    total["cache_write"], total["cache_write"] * _DEFAULT_PRICE["cache_write"] / M, _DEFAULT_PRICE["cache_write"]),
            ("cache_write_1h", cache_1h_total,       cache_1h_total       * _DEFAULT_PRICE["cache_write"] / M, _DEFAULT_PRICE["cache_write"]),
            ("cache_write_5m", cache_5m_total,       cache_5m_total       * _DEFAULT_PRICE["cache_write"] / M, _DEFAULT_PRICE["cache_write"]),
            ("output",         total["output"],      total["output"]      * _DEFAULT_PRICE["output"]      / M, _DEFAULT_PRICE["output"]),
            ("web_search",     total["web_search"],  0.0, 0),
            ("web_fetch",      total["web_fetch"],   0.0, 0),
        ]
        print(f"{'Type':<18} {'Tokens':>12} {'$/MTok':>8} {'Cost':>10}")
        print("─" * 52)
        for name, tokens, cost, rate in rows:
            rate_str = f"{rate:.2f}" if rate else "-"
            cost_str = f"${cost:>9.4f}" if rate else f"{'(n/a)':>10}"
            print(f"{name:<18} {tokens:>12,} {rate_str:>8} {cost_str}")
        print("─" * 52)
        print(f"{'Total':<18} {'':>12} {'':>8} ${total_cost:>9.4f}")
    else:
        model_w = max((len(r["model"].replace("claude-","")) for r in calls), default=8)
        show_session = no_session_arg

        sess_col = f"  {'Session':<8}" if show_session else ""
        if detail:
            hdr = f"  {'#':>3}  {'Timestamp':<19}{sess_col}  {'Model':<{model_w}}  {'In':>6}  {'CacheRead':>7}  {'CacheWrite':>7}  {'1h':>7}  {'5m':>7}  {'Out':>6}  {'🔍':>2}  {'🌐':>2}  {'Tier':<8}  {'Speed':<8}  {'Cost':>7}"
        else:
            hdr = f"  {'#':>3}  {'Timestamp':<19}{sess_col}  {'Model':<{model_w}}  {'In':>12}  {'CacheRead':>14}  {'CacheWrite':>15}  {'Out':>13}  {'Cost':>8}"
        print(hdr)
        print("─" * len(hdr))

        for i, r in enumerate(calls, 1):
            cost = calc_cost(r)
            model_short = r["model"].replace("claude-", "")
            ts = r["timestamp"][:19].replace("T", " ") if r["timestamp"] else "n/a"
            sc = f"  {r.get('session',''):<8}" if show_session else ""
            if detail:
                ws = str(r["web_search"]) if r["web_search"] else "-"
                wf = str(r["web_fetch"])  if r["web_fetch"]  else "-"
                print(f"  {i:>3}  {ts:<19}{sc}  {model_short:<{model_w}}  {fmt_k(r['input']):>6}  {fmt_k(r['cache_read']):>7}  {fmt_k(r['cache_write']):>7}  {fmt_k(r['cache_1h']):>7}  {fmt_k(r['cache_5m']):>7}  {fmt_k(r['output']):>6}  {ws:>2}  {wf:>2}  {r['tier']:<8}  {r['speed']:<8}  ${cost:.4f}")
            else:
                p = price_for(r.get("model", ""))
                M = 1_000_000
                in_c  = fmt_kc(r['input'],       r['input']       * p['input']       / M)
                cr_c  = fmt_kc(r['cache_read'],  r['cache_read']  * p['cache_read']  / M)
                cw_c  = fmt_kc(r['cache_write'], r['cache_write'] * p['cache_write'] / M)
                out_c = fmt_kc(r['output'],      r['output']      * p['output']      / M)
                print(f"  {i:>3}  {ts:<19}{sc}  {model_short:<{model_w}}  {in_c:>12}  {cr_c:>14}  {cw_c:>14}  {out_c:>13}  ${cost:.4f}")

        print("─" * len(hdr))
        if len(calls) > 1:
            t_model = ""
            tc = f"  {'':8}" if show_session else ""
            blank = f"  {'':>3}  {'':19}{tc}"
            if detail:
                print(f"{blank}  {'Total':<{model_w}}  {fmt_k(total['input']):>6}  {fmt_k(total['cache_read']):>7}  {fmt_k(total['cache_write']):>7}  {'':>7}  {'':>7}  {fmt_k(total['output']):>6}  {'':>2}  {'':>2}  {'':>8}  {'':>8}  ${total_cost:.4f}")
            else:
                in_tc  = fmt_kc(total['input'],       total_costs['input'])
                cr_tc  = fmt_kc(total['cache_read'],  total_costs['cache_read'])
                cw_tc  = fmt_kc(total['cache_write'], total_costs['cache_write'])
                out_tc = fmt_kc(total['output'],      total_costs['output'])
                print(f"{blank}  {'Total':<{model_w}}  {in_tc:>12}  {cr_tc:>14}  {cw_tc:>14}  {out_tc:>13}  ${total_cost:.4f}")
        if current_flag and calls:
            last = calls[-1]
            ctx = last['input'] + last['cache_read']
            print(f"\n  context now: ~{fmt_k(ctx)} tokens  (In + CacheRead of last call)")
    print()

    if buf:
        sys.stdout = sys.__stdout__
        output = buf.getvalue()
        if pager:
            pipe_to_pager(output)
        else:
            paginate(output.splitlines(), page_size)

if __name__ == "__main__":
    main()
