#!/usr/bin/env python3
"""Per-request token usage breakdown for current Claude Code session."""

import io
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_BUILTIN_PRICES = {
    "claude-fable-5-1":  {"input": 10.00, "cache_write": 12.50, "cache_read": 0.25, "output": 50.00},
    "claude-mythos-5-1": {"input": 10.00, "cache_write": 12.50, "cache_read": 0.25, "output": 50.00},  # cache_read unconfirmed for this model specifically — assumed same as Fable 5.1's tier
    "claude-fable-5":    {"input": 10.00, "cache_write": 12.50, "cache_read": 1.00, "output": 50.00},
    "claude-mythos-5":   {"input": 10.00, "cache_write": 12.50, "cache_read": 1.00, "output": 50.00},
    "claude-opus-5":     {"input":  5.00, "cache_write":  6.25, "cache_read": 0.50, "output": 25.00},
    "claude-opus-4-8":   {"input":  5.00, "cache_write":  6.25, "cache_read": 0.50, "output": 25.00},
    "claude-opus-4-7":   {"input":  5.00, "cache_write":  6.25, "cache_read": 0.50, "output": 25.00},
    "claude-opus-4-6":   {"input":  5.00, "cache_write":  6.25, "cache_read": 0.50, "output": 25.00},
    "claude-sonnet-5":   {"input":  2.00, "cache_write":  2.50, "cache_read": 0.20, "output": 10.00},
    "claude-sonnet-4-6": {"input":  3.00, "cache_write":  3.75, "cache_read": 0.30, "output": 15.00},
    "claude-haiku-4-5":  {"input":  1.00, "cache_write":  1.25, "cache_read": 0.10, "output":  5.00},
}
_DEFAULT_PRICE = {"input": 3.00, "cache_write": 3.75, "cache_read": 0.30, "output": 15.00}

_PRICES_FILE = Path.home() / ".claude" / "scripts" / "prices.json"
_RATE_WINDOW_SECONDS = 20 * 60  # "current pace" looks at the last 20 min, not the whole 5h window

_RL_STATE_FILE = Path.home() / ".claude" / "scripts" / "rate-limits-state.json"
_RL_STALE_SECONDS = 30 * 60  # ignore official data if statusLine hasn't fired in 30 min

# 7d moves ~100x slower than 5h (a whole week vs a whole 5h window), so its
# history needs a coarser throttle, a much longer retention window, and a
# much longer minimum span before a rate is trustworthy.
_SEVEN_D_THROTTLE_SECONDS = 3600        # one sample per hour is plenty
_SEVEN_D_WINDOW_SECONDS = 48 * 3600     # look at the last 48h for "current pace"
_SEVEN_D_MIN_SPAN_SECONDS = 2 * 3600    # need 2h of real spread before trusting the rate

_CTX_NUDGE_THRESHOLD = 50  # fallback floor: below this, never nudge regardless of trend
_CTX_RATE_WINDOW_SECONDS = 15 * 60  # ctx can swing fast within one session; shorter window than 5h's
_CTX_MIN_SPAN_SECONDS = 120         # need 2 min of real spread before trusting the ctx growth rate
_CTX_NUDGE_ETA_MIN = 15             # nudge when projected time-to-100% ctx is under this many minutes
_CTX_HARD_FLOOR = 85                # nudge regardless of trend once ctx is this high (no time to react)

# "Entry fee" = the fixed system-prompt+tools+skills cost every fresh session
# pays on its first call, before any real work happens. Grows quietly as
# skills/MCP servers/CLAUDE.md accumulate; this is a passive per-model
# fixed-anchor check (not rolling) so accepting a jump is a deliberate act.
_ENTRY_FEE_FILE = Path.home() / ".claude" / "scripts" / "entry-fee-baseline.json"
_ENTRY_FEE_ALERT_PCT = 20

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
    projects = Path.home() / ".claude" / "projects"
    if session_id:
        for p in projects.rglob(f"{session_id}*.jsonl"):
            return p
        print(f"Session {session_id} not found")
        sys.exit(1)
    files = list(projects.rglob("*.jsonl"))
    if not files:
        print("No sessions found")
        sys.exit(1)
    return max(files, key=lambda f: f.stat().st_mtime)


def get_session_desc(path, max_msgs=3):
    snippets = []
    try:
        with open(path) as f:
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
    return "、".join(snippets) if snippets else ""


def list_sessions(sort_by_cost=False, last_n=20, with_desc=False):
    projects = Path.home() / ".claude" / "projects"
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
    label = f"latest {len(rows)} (of {total})" if total > last_n else f"{len(rows)} sessions"
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
    with open(path) as f:
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
    projects = Path.home() / ".claude" / "projects"
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
    with open(path) as f:
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

    # Build uuid→entry map for prompt lookup
    uuid_map = {e.get("uuid"): e for e in entries if e.get("uuid")}

    calls = []
    last_user_prompt = ""

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

            calls.append({
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
            })

    return calls


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
    return {"updated_at": None, "five_hour": None, "seven_day": None, "history": [], "history_7d": []}


def _save_rl_state(state):
    try:
        _RL_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _RL_STATE_FILE.write_text(json.dumps(state))
    except Exception:
        pass


def statusline_hook():
    """Read Claude Code's statusLine JSON payload from stdin, cache the
    official rate_limits it contains, and print the visible status line
    (the row is reserved either way once this hook is configured, so it's
    printed rather than left blank)."""
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
        # statusLine can fire many times a minute; throttle history points
        # so a 20-min window isn't just noise from near-identical readings.
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

    # Claude Code reserves the statusLine row whenever one is configured at
    # all — printing nothing still leaves a blank row, it doesn't remove
    # it. So put something useful there instead of wasting it.
    model_name = (data.get("model") or {}).get("display_name", "")
    ctx_pct = (data.get("context_window") or {}).get("used_percentage")

    parts = [model_name] if model_name else []
    if ctx_pct is not None:
        ctx_part = f"ctx:{ctx_pct:.0f}%"
        # Prompt cache TTL is ~1h. A big context that sits idle past that
        # (end of day, switching tasks) means whoever resumes it eats a
        # full reprocess — cache_write on the entire thing, not a cheap
        # cache_read. Rather than a flat "% above X" trip-wire, track recent
        # growth and project it forward — same "burn rate vs remaining
        # runway" idea as the 5h/7d runway line below, applied to ctx
        # instead of quota.
        ctx_hist = state.get("ctx_history", [])
        if not ctx_hist or (now - datetime.fromisoformat(ctx_hist[-1][0])) >= timedelta(seconds=30):
            ctx_hist.append([now.isoformat(), ctx_pct])
        ctx_cutoff = now - timedelta(seconds=_CTX_RATE_WINDOW_SECONDS)
        ctx_hist = [[t, p] for t, p in ctx_hist if datetime.fromisoformat(t) >= ctx_cutoff]
        state["ctx_history"] = ctx_hist
        _save_rl_state(state)  # the save above (before this block) runs before ctx_history is computed

        eta_min = _ctx_eta_minutes(ctx_hist, now)
        nudge = False
        if ctx_pct >= _CTX_HARD_FLOOR:
            nudge = True
        elif ctx_pct >= _CTX_NUDGE_THRESHOLD and eta_min is not None and eta_min < _CTX_NUDGE_ETA_MIN:
            nudge = True
        if nudge:
            ctx_part += "  💡ctx high, consider /oct-nap before stepping away"
        parts.append(ctx_part)

    eta = official_eta_line()
    if eta:
        parts.append(eta.replace("📈 ", ""))

    print("  ".join(parts))


def _fmt_minutes(m):
    if m < 60:
        return f"{m:.0f}m"
    if m < 1440:
        return f"{m/60:.1f}h"
    return f"{m/1440:.1f}d"


def _ctx_eta_minutes(hist, now):
    """Projected minutes until ctx% hits 100 at the recent growth rate, or
    None if there isn't enough history yet or ctx isn't currently growing."""
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


def _reset_eta_segment(pct, resets_at, hist, now, min_span_min):
    """reset:X / runway:Y for one rate-limit window (5h or 7d) — "runway"
    (how much longer you can keep going at the current pace before hitting
    the cap), not a generic ETA. Returns None when there's neither a reset
    time nor enough history to say anything."""
    remain_min = None
    if resets_at:
        reset_dt = datetime.fromtimestamp(resets_at, tz=timezone.utc)
        m = (reset_dt - now).total_seconds() / 60
        if m > 0:
            remain_min = m

    eta_min = None
    eta_note = "sampling"
    if len(hist) >= 2:
        t0, p0 = hist[0]
        span_min = (now - datetime.fromisoformat(t0)).total_seconds() / 60
        # official % is quantized (whole points) and can jitter slightly, so
        # a short span produces a near-meaningless (often zero) delta —
        # require real spread before trusting the rate.
        if span_min < min_span_min:
            wait_min = min_span_min - span_min
            eta_note = f"sampling, {_fmt_minutes(wait_min)} more needed"
        else:
            rate = (pct - p0) / span_min
            if rate <= 1e-6:
                eta_note = "usage flat"
            else:
                eta_min = (100 - pct) / rate

    if remain_min is None and eta_min is None:
        return None

    reset_str = _fmt_minutes(remain_min) if remain_min is not None else "?"
    eta_str = _fmt_minutes(eta_min) if eta_min is not None else eta_note

    # the comparison itself is the point: does the window empty out before
    # you'd burn through it at this pace, or the other way around? Gated on
    # pct > 60 too — below that, a rate-based projection this far out is too
    # noisy to be worth flagging.
    verdict = ""
    fired = False
    if (
        remain_min is not None
        and eta_min is not None
        and eta_min < remain_min
        and pct > 60
    ):
        verdict = "  !"
        fired = True

    return f"reset:{reset_str} / runway:{eta_str}{verdict}", fired


def official_eta_line():
    """Prefer Anthropic's real rate_limits (captured via the statusLine
    hook) over the self-calibrated estimate. Returns None if no fresh
    official data is available, so the caller can fall back."""
    state = _load_rl_state()
    updated_at = state.get("updated_at")
    if not updated_at:
        return None
    now = datetime.now(timezone.utc)
    if now - datetime.fromisoformat(updated_at) > timedelta(seconds=_RL_STALE_SECONDS):
        return None
    five = state.get("five_hour")
    if not five or five.get("used_percentage") is None:
        return None

    pct = five["used_percentage"]
    line = f"📈 5h window:{pct:.0f}%"
    any_fired = False

    seg5 = _reset_eta_segment(
        pct, five.get("resets_at"), state.get("history", []), now,
        min_span_min=3,
    )
    if seg5 is None:
        line += "  (sampling...)"
    else:
        seg5_text, fired5 = seg5
        line += f"  {seg5_text}"
        any_fired = any_fired or fired5

    seven = state.get("seven_day")
    if seven and seven.get("used_percentage") is not None:
        pct7 = seven["used_percentage"]
        line += f"  |  7d:{pct7:.0f}%"
        seg7 = _reset_eta_segment(
            pct7, seven.get("resets_at"), state.get("history_7d", []), now,
            min_span_min=120,
        )
        if seg7 is not None:
            seg7_text, fired7 = seg7
            line += f"  {seg7_text}"
            any_fired = any_fired or fired7

    if any_fired:
        line += "  |  !: at this pace you'll burn through the quota before it resets"

    return line


_MODEL_DATE_SUFFIX_RE = re.compile(r"-\d{8}$")


def price_for(model):
    """Look up per-token prices for a model. Falls back to stripping a
    trailing dated-snapshot suffix (e.g. -20251001) before giving up to
    _DEFAULT_PRICE — a dated snapshot bills the same as its base model, but
    an exact-match-only lookup would silently mis-price it (this is how
    every Haiku call ended up priced at Sonnet rates before this fix)."""
    if model in PRICES:
        return PRICES[model]
    base = _MODEL_DATE_SUFFIX_RE.sub("", model)
    return PRICES.get(base, _DEFAULT_PRICE)


def calc_cost(r):
    p = price_for(r.get("model", ""))
    M = 1_000_000
    return (
        r["input"]       * p["input"]       / M +
        r["cache_write"] * p["cache_write"] / M +
        r["cache_read"]  * p["cache_read"]  / M +
        r["output"]      * p["output"]      / M
    )


def _entry_fee_now():
    """Return (model, fee_tokens) for the current session's first call, or
    (None, None) if the session has no calls yet."""
    path = find_session()
    calls = parse_calls(path)
    if not calls:
        return None, None
    first = calls[0]
    fee = first["input"] + first["cache_write"]
    return first["model"], fee


def _load_entry_fee_baseline():
    if _ENTRY_FEE_FILE.exists():
        try:
            return json.loads(_ENTRY_FEE_FILE.read_text())
        except Exception:
            pass
    return {}


def entry_fee_check():
    """Passive check for /oct-wake: print one line only when this session's
    entry fee has grown >_ENTRY_FEE_ALERT_PCT vs the stored per-model
    baseline. Silent on first sighting of a model (baseline just gets set),
    silent when within threshold. Fixed anchor, not rolling — stays quiet
    until the user explicitly accepts a new baseline (--entry-fee-accept)."""
    model, fee = _entry_fee_now()
    if model is None:
        return
    baseline = _load_entry_fee_baseline()
    base = baseline.get(model)
    if base is None:
        baseline[model] = fee
        _ENTRY_FEE_FILE.write_text(json.dumps(baseline, indent=2))
        return
    if base <= 0:
        return
    pct = (fee - base) / base * 100
    if pct >= _ENTRY_FEE_ALERT_PCT:
        print(f"💡 Entry fee went from {fmt_k(base)} to {fmt_k(fee)} (+{pct:.0f}%) — "
              f"maybe a new skill/MCP server? Accept as the new baseline? ({model})")


def entry_fee_accept():
    model, fee = _entry_fee_now()
    if model is None:
        print("No calls in the current session yet — can't set a baseline")
        return
    baseline = _load_entry_fee_baseline()
    baseline[model] = fee
    _ENTRY_FEE_FILE.write_text(json.dumps(baseline, indent=2))
    print(f"✅ Accepted new baseline: {model} = {fmt_k(fee)}")


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


_HABIT_LONG_ANSWER_CHARS = 1200   # an answer this long is "a wall" for follow-up purposes
_HABIT_LONG_ANSWER_STEPS = 5      # or this many numbered lines — a step-by-step dump
_HABIT_SHORT_QUESTION_CHARS = 60  # a follow-up this short right after a wall = didn't land
_HABIT_FAT_CTX_TOKENS = 100_000   # cache_read above this: even a one-word reply costs real money
_HABIT_TINY_PROMPT_CHARS = 30
_HABIT_FAT_SESSION_END = 80_000   # session ended this fat without a nap = cold resume later
_HABIT_MAX_EXAMPLES = 2
_HABIT_POST_COMPACT_WINDOW_SEC = 1800  # a correction this soon after auto-compact counts as "right after"
_HABIT_MIN_POST_COMPACT_CORRECTIONS = 2
_HABIT_SLOW_SCAN_SEC = 8  # the scan itself took this long — it's supposed to be a cheap local pass

_QUESTION_RE = re.compile(r"[?？]|嗎|是不是|什麼意思|哪一?台|哪個|which|what do you mean", re.I)
_STEP_LINE_RE = re.compile(r"^\s*\d+[\.\)、]\s", re.M)
_CORRECTION_RE = re.compile(
    r"^(不要|不用|別|不是|停|不對|錯了|我說過|又來|再說一次|don'?t|stop|no[,，]|wrong|not that)", re.I)


def _iso_ts(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return None


def _session_turns(path):
    """Collapse a transcript into user→assistant turns on the main chain:
    (user_text, assistant_text, cache_read_of_last_call, turn_cost, ts).
    Also returns sorted timestamps of any auto-compact boundaries — same
    single file pass, no second read."""
    entries = []
    seen = set()
    compact_ts = []
    with open(path) as f:
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
                continue  # tool_result, not a human message
            text = get_text(content).strip()
            if not text or text.startswith("<"):
                continue
            if cur:
                turns.append(cur)
            cur = {"user": text, "asst": "", "cache_read": 0, "cost": 0.0,
                   "reread": 0.0, "reread_ctx": 0, "ts": e.get("timestamp", "")}
        elif t == "assistant" and cur is not None:
            msg = e.get("message", {})
            content = msg.get("content", [])
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "text":
                        cur["asst"] += b.get("text", "")
            usage = msg.get("usage")
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
                    # first call of the turn: what it cost just to re-read
                    # the context before doing anything — the "waste" part,
                    # as opposed to the work the turn then went on to do.
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


def habits_report(days=7):
    """Scan recent transcripts for spending patterns that a one-line memory
    rule could fix. Pure python — Claude only ever sees this summary."""
    _scan_start = time.monotonic()
    projects = Path.home() / ".claude" / "projects"
    cutoff = datetime.now().timestamp() - days * 86400
    files = [f for f in projects.rglob("*.jsonl") if f.stat().st_mtime >= cutoff]

    summaries = Path.home() / ".claude" / "summaries"
    nap_times = []
    if summaries.exists():
        for f in list(summaries.glob("*.md")) + list((summaries / "archive").glob("*.md")):
            nap_times.append(f.stat().st_mtime)

    wall_then_q = []     # (cost, sid, ts, follow-up text)
    fat_chatter = []     # (cost, sid, ts, prompt)
    corrections = []     # (sid, ts, text)
    fat_no_nap = []      # (sid, cache_read, end_ts)
    post_compact_corr = []  # (sid, ts, text, session_compact_count) - correction soon after an auto-compact
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
        out.append(f"1. Long answer, immediate short follow-up question  ×{len(wall_then_q)}  re-read cost alone ≈${cost:.2f}")
        out.append("   Claude dumps a wall of text (or 5+ steps) in one go, and you have to ask a question halfway through. Every follow-up re-reads the whole conversation.")
        for c, sid, ts, txt in sorted(wall_then_q, reverse=True)[:_HABIT_MAX_EXAMPLES]:
            out.append(ex_line(sid, ts, txt))
        out.append("   Suggested rule: give operational steps one at a time, name the target, wait for a report before the next step; write long conclusions to a file and share only the path.\n")

    if fat_chatter:
        fired += 1
        cost = sum(c for c, *_ in fat_chatter)
        out.append(f"2. Short back-and-forth on an already-fat context  ×{len(fat_chatter)}  re-read cost alone ≈${cost:.2f}")
        out.append(f"   Once context passes {_HABIT_FAT_CTX_TOKENS // 1000}K, even a one-word reply costs a full re-read.")
        for c, sid, ts, txt, ctx in sorted(fat_chatter, reverse=True)[:_HABIT_MAX_EXAMPLES]:
            out.append(ex_line(sid, ts, txt) + f"  ctx {fmt_k(ctx)} → ${c:.2f} just to read this line")
        out.append("   Suggested habit: once ctx passes half, /oct-nap then /clear — pick up with the note instead of dragging a fat conversation along.\n")

    if len(corrections) >= 3:
        fired += 1
        by_sess = {}
        for sid, ts, txt in corrections:
            by_sess.setdefault(sid, []).append((ts, txt))
        out.append(f"3. Repeated corrections to Claude  ×{len(corrections)}, across {len(by_sess)} sessions")
        out.append("   The same correction said a second time means it belongs in long-term memory, not a one-off message.")
        for sid, ts, txt in corrections[-_HABIT_MAX_EXAMPLES:]:
            out.append(ex_line(sid, ts, txt))
        out.append("   Suggestion: turn the recurring correction into a feedback memory (rule + why + when it applies).\n")

    if fat_no_nap:
        fired += 1
        out.append(f"4. Fat session ended without a checkpoint  ×{len(fat_no_nap)}")
        out.append(f"   Context was still {_HABIT_FAT_SESSION_END // 1000}K+ at the end — a later --resume means a full cold re-read.")
        for sid, cr, end in sorted(fat_no_nap, key=lambda x: -x[1])[:_HABIT_MAX_EXAMPLES]:
            out.append(f"      · {sid}  ctx {fmt_k(cr)}  {datetime.fromtimestamp(end).strftime('%m-%d %H:%M')}")
        out.append("   Suggested habit: /oct-nap (or /oct-sleep) before stepping away — next time /oct-wake only reads a 1-2k note.\n")

    if len(post_compact_corr) >= _HABIT_MIN_POST_COMPACT_CORRECTIONS:
        fired += 1
        by_sess = {}
        for sid, ts, txt, ccount in post_compact_corr:
            by_sess.setdefault(sid, []).append((ts, txt, ccount))
        out.append(f"5. Corrected again right after an auto-compact  ×{len(post_compact_corr)}, across {len(by_sess)} sessions")
        out.append("   Shortly after an auto-compact, the same kind of thing had to be corrected again — as if the rule was living in "
                    "the conversation and got diluted by the compaction instead of actually being retained. (This is a timing "
                    "coincidence check, not proof the two are related — the more times a session auto-compacted that day, the more "
                    "likely a coincidental hit is; discount examples from high-compact-count sessions accordingly.)")
        for sid, ts, txt, ccount in post_compact_corr[-_HABIT_MAX_EXAMPLES:]:
            out.append(ex_line(sid, ts, txt) + f"  (that session auto-compacted {ccount}x that day)")
        out.append("   Suggestion: move rules like this into CLAUDE.md (global or that project's own) instead of relying on them surviving compaction inside the conversation.\n")

    scan_secs = time.monotonic() - _scan_start
    if scan_secs >= _HABIT_SLOW_SCAN_SEC:
        out.append(f"⏱️ This scan itself took {scan_secs:.1f}s ({len(files)} sessions, last {days} days) — "
                    "this tool is supposed to be a cheap local pass, so that's slower than it should be.")
        out.append("   If this keeps happening, please report it: https://github.com/sunososobro-hub/claude-octopus/issues"
                    " (just this line's numbers is enough — no need to paste any conversation content)\n")

    if fired == 0:
        out.append(f"✅ No obvious waste patterns in the last {days} days.")
    else:
        out.append("Which of these should be saved as long-term memory? (e.g. \"1 3\" / \"all of them\" / \"none\")")
    print("\n".join(out))


def main():
    args = sys.argv[1:]

    if args and args[0] == "--statusline-hook":
        statusline_hook()
        sys.exit(0)

    if args and args[0] == "--entry-fee-check":
        entry_fee_check()
        sys.exit(0)

    if args and args[0] == "--entry-fee-accept":
        entry_fee_accept()
        sys.exit(0)

    # --set-price <model> <input> <output>  (cache rates auto-derived)
    if len(args) >= 4 and args[0] == "--set-price":
        model = args[1] if args[1].startswith("claude-") else f"claude-{args[1]}"
        inp, out = float(args[2]), float(args[3])
        entry = {"input": inp, "cache_write": round(inp * 1.25, 4),
                 "cache_read": round(inp * 0.10, 4), "output": out}
        data = json.loads(_PRICES_FILE.read_text()) if _PRICES_FILE.exists() else {}
        data[model] = entry
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
        path = find_session()
        calls = parse_calls(path)
        if not calls:
            sys.exit(0)
        r = calls[-1]
        cost = calc_cost(r)
        p = price_for(r.get("model", ""))
        M = 1_000_000
        in_c  = fmt_kc(r['input'],       r['input']       * p['input']       / M)
        cr_c  = fmt_kc(r['cache_read'],  r['cache_read']  * p['cache_read']  / M)
        cw_c  = fmt_kc(r['cache_write'], r['cache_write'] * p['cache_write'] / M)
        out_c = fmt_kc(r['output'],      r['output']      * p['output']      / M)
        print(f"💰 In:{in_c}  CR:{cr_c}  CW:{cw_c}  Out:{out_c}  =${cost:.4f}")
        # Model name, ctx%, and 5h/7d reset+runway are NOT repeated here — all
        # already always-visible in the statusLine (see statusline_hook).
        # One surface, one number, per metric.
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
        label = f"latest {shown} (of {total_calls})"
    elif last_n:
        label = f"latest {shown}"
    else:
        label = f"{shown} API calls"

    # Aggregate totals
    total = {k: 0 for k in ("input","cache_read","cache_write","output","web_search","web_fetch")}
    total_costs = {"input": 0.0, "cache_read": 0.0, "cache_write": 0.0, "output": 0.0}
    for r in calls:
        for k in total:
            total[k] += r[k]
        p = price_for(r.get("model", ""))
        M = 1_000_000
        total_costs["input"]       += r["input"]       * p["input"]       / M
        total_costs["cache_read"]  += r["cache_read"]  * p["cache_read"]  / M
        total_costs["cache_write"] += r["cache_write"] * p["cache_write"] / M
        total_costs["output"]      += r["output"]      * p["output"]      / M

    total_cost = sum(total_costs.values())

    buf = io.StringIO() if (pager or page_size) else None
    if buf:
        sys.stdout = buf

    print(f"\n📊 oct-checkup  |  {label}\n")

    if summary:
        # Aggregated summary table
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
        # Table view
        model_w = max((len(r["model"].replace("claude-","")) for r in calls), default=8)
        show_session = no_session_arg  # show Session col when browsing all sessions

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
