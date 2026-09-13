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

_FIVE_HOUR_MIN = 5 * 60       # fixed window length, for the average-pace-since-start signal
_SEVEN_DAY_MIN = 7 * 24 * 60

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
    label = f"最新 {len(rows)} 筆（共 {total} 筆）" if total > last_n else f"{len(rows)} sessions"
    if with_desc:
        print(f"\n{'Session':<12}  {'Date':<10}  {'Calls':>5}  {'Cost':>8}  描述")
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
    # it. So put something useful there instead of wasting it: model name
    # + per-window icon+duration + ctx% (see _pulse_compact). The fuller
    # bar view (dashes, │ center marks) lives in `--pulse-detail` — this
    # row stays numbers-not-bars so it's still a glance, not a read.
    model_name = (data.get("model") or {}).get("display_name", "")
    ctx_pct = (data.get("context_window") or {}).get("used_percentage")

    if ctx_pct is not None:
        # Prompt cache TTL is ~1h. A big context that sits idle past that
        # (end of day, switching tasks) means whoever resumes it eats a
        # full reprocess — cache_write on the entire thing, not a cheap
        # cache_read. Rather than a flat "% above X" trip-wire, track recent
        # growth and project it forward — same "burn rate vs remaining
        # runway" idea as the rate-limit bars, applied to ctx instead of
        # quota.
        ctx_hist = state.get("ctx_history", [])
        if not ctx_hist or (now - datetime.fromisoformat(ctx_hist[-1][0])) >= timedelta(seconds=30):
            ctx_hist.append([now.isoformat(), ctx_pct])
        ctx_cutoff = now - timedelta(seconds=_CTX_RATE_WINDOW_SECONDS)
        ctx_hist = [[t, p] for t, p in ctx_hist if datetime.fromisoformat(t) >= ctx_cutoff]
        state["ctx_history"] = ctx_hist
        _save_rl_state(state)  # the save above (line 387) runs before this block computes ctx_history

    compact = _pulse_compact(state, now)
    print(f"{model_name}  {compact}" if model_name and compact else (compact or model_name))


_ICON_RANK = {"🔋": 0, "⚡": 1, "🪫": 2}


def _margin_icon(pct, margin_frac):
    """Per-window severity icon from the schedule margin itself, not a
    separate boolean: 🔋 safe (bar would grow right, or no rate data yet)
    / ⚡ mild (burning ahead of schedule, but within half the balance
    point) / 🪫 severe (past half the balance point — heading for empty
    well before reset). margin_frac's danger side is naturally bounded in
    [-1, 0) (eta_min can't go below 0), so -0.5 is a real halfway point,
    not an arbitrary scale. Gated on pct > 60 — below that, a rate
    projection this far out is too noisy to act on."""
    if margin_frac is None or margin_frac >= 0 or pct <= 60:
        return "🔋"
    return "⚡" if margin_frac >= -0.5 else "🪫"


def _battery(eta_str, margin_frac, icon, half_width=2):
    """Center-anchored bar: how far ahead of or behind schedule the current
    burn rate is — the number that matters (可撐, projected time-to-100%)
    lives right at the bar's tip instead of trailing after it as separate
    text, and the tip itself is the battery-style severity icon instead of
    a plain arrow. margin_frac > 0 means the quota would last longer than
    the time left (safe, grows right); < 0 means it would run out before
    the window resets (grows left toward empty). None (no rate data yet)
    renders as a flat center line with whatever note explains the gap —
    there's nothing to report yet, not "on schedule"."""
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


def _avg_pace_eta_min(pct, remain_min, window_total_min):
    """Projected minutes-to-100%-used from the plain average pace since
    this window started (pct ÷ elapsed time) — no sampling/history
    needed, available from the first minute of a window. This smooths out
    exactly what a short recent-rate lookback overreacts to: a busy
    morning, a quiet weekend, any human non-uniform pacing — a brief
    burst doesn't move this number much because it's averaged over the
    whole window-so-far, not just the last few minutes. None if the
    window just started (elapsed too small for the ratio to mean
    anything) or pct is 0 (nothing to divide by yet)."""
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
    """Raw numbers behind the reset/可撐 comparison for one rate-limit
    window: (remain_min, eta_min, eta_note). `eta_min` is the projected
    minutes-to-100%-used at the current *recent* pace (last 20min for 5h,
    last 48h for 7d) — None if there's not enough history yet (`eta_note`
    explains why). See `_avg_pace_eta_min` for the complementary
    whole-window-average signal; `_rate_windows` combines both."""
    remain_min = None
    if resets_at:
        reset_dt = datetime.fromtimestamp(resets_at, tz=timezone.utc)
        m = (reset_dt - now).total_seconds() / 60
        if m > 0:
            remain_min = m

    eta_min = None
    eta_note = "⏳"  # just started sampling, nothing else worth saying yet
    if len(hist) >= 2:
        t0, p0 = hist[0]
        span_min = (now - datetime.fromisoformat(t0)).total_seconds() / 60
        # official % is quantized (whole points) and can jitter slightly, so
        # a short span produces a near-meaningless (often zero) delta —
        # require real spread before trusting the rate.
        if span_min < min_span_min:
            wait_min = min_span_min - span_min
            eta_note = f"⏳{_fmt_minutes(wait_min)}"
        else:
            rate = (pct - p0) / span_min
            if rate <= 1e-6:
                eta_note = "∞"  # flat usage — at this (non-)rate it never hits 100%
            else:
                eta_min = (100 - pct) / rate

    return remain_min, eta_min, eta_note


def _rate_windows(state, now):
    """Per-window (5h, then 7d if present) computed fields as a list of
    dicts: label, pct, icon, eta_str, remain_str, bar. Empty list if
    there's no fresh official data (never seen, or statusLine hasn't
    fired in 30 min). Shared by the compact statusLine and --pulse-detail
    so both read off the same numbers instead of two slightly different
    derivations."""
    updated_at = state.get("updated_at")
    if not updated_at:
        return []
    if now - datetime.fromisoformat(updated_at) > timedelta(seconds=_RL_STALE_SECONDS):
        return []
    five = state.get("five_hour")
    if not five or five.get("used_percentage") is None:
        return []

    windows = []

    def add_window(label, pct, resets_at, hist, min_span_min, window_total_min):
        remain_min, eta_recent_min, eta_note = _reset_eta_raw(
            pct, resets_at, hist, now, min_span_min
        )
        eta_avg_min = _avg_pace_eta_min(pct, remain_min, window_total_min)
        # Only escalate when the recent burst *and* the whole-window average
        # both agree it's a problem — max(), not min(): a brief fast patch
        # that the average absorbs stays 🔋, and a slow patch that the
        # average still finds worrying doesn't get waved off just because
        # this exact moment happens to be calm. Either signal alone was too
        # noisy in one direction or the other.
        if eta_recent_min is not None and eta_avg_min is not None:
            eta_min = max(eta_recent_min, eta_avg_min)
        else:
            eta_min = eta_recent_min if eta_recent_min is not None else eta_avg_min

        margin_frac = None
        if remain_min is not None and eta_min is not None and remain_min > 1e-9:
            margin_frac = (eta_min - remain_min) / remain_min
        icon = _margin_icon(pct, margin_frac)
        eta_str = _fmt_minutes(eta_min) if eta_min is not None else eta_note
        windows.append({
            "label": label, "pct": pct, "icon": icon, "eta_str": eta_str,
            "remain_str": _fmt_minutes(remain_min) if remain_min is not None else "?",
            "bar": _battery(eta_str, margin_frac, icon),
        })

    add_window("5h", five["used_percentage"], five.get("resets_at"), state.get("history", []), min_span_min=3, window_total_min=_FIVE_HOUR_MIN)

    seven = state.get("seven_day")
    if seven and seven.get("used_percentage") is not None:
        add_window("7d", seven["used_percentage"], seven.get("resets_at"), state.get("history_7d", []), min_span_min=120, window_total_min=_SEVEN_DAY_MIN)

    return windows


def _ctx_nudge(state, now):
    """Whether ctx is high enough (or growing fast enough) to warrant a
    /oct-nap suggestion before this session pauses. Reads `state` only —
    no side effects — so both the statusLine hook and --pulse-detail can
    call it without re-deriving ctx_history. Returns (nudge, ctx_pct);
    ctx_pct is None if there's no ctx_history yet."""
    ctx_hist = state.get("ctx_history", [])
    if not ctx_hist:
        return False, None
    ctx_pct = ctx_hist[-1][1]
    eta_min = _ctx_eta_minutes(ctx_hist, now)
    if ctx_pct >= _CTX_HARD_FLOOR:
        return True, ctx_pct
    if ctx_pct >= _CTX_NUDGE_THRESHOLD and eta_min is not None and eta_min < _CTX_NUDGE_ETA_MIN:
        return True, ctx_pct
    return False, ctx_pct


def _pulse_compact(state, now):
    """The persistent statusLine content: each rate-limit window's own
    icon between the two numbers that are actually being compared — time
    left until reset, and 可撐 (projected time-to-100%-used at the
    current pace) — both in the same unit on purpose. A pct next to a
    duration forces a unit conversion in the reader's head; two durations
    don't, and time-vs-time *is* the comparison the icon itself already
    encodes (see _margin_icon), so showing it in the same unit makes the
    icon's verdict checkable at a glance instead of taken on faith. Real
    pct%, for whoever wants the never-wrong official number as a separate
    sanity check, lives in --pulse-detail. Plus ctx as a number that's
    always shown, not only once it's high enough to matter. No
    bars/dashes here — those live in --pulse-detail; this is the compact
    middle ground between "just an icon" (not enough to act on) and the
    full bar view (more than a glance needs)."""
    windows = _rate_windows(state, now)
    rate_part = "  ".join(f"{w['label']} {w['remain_str']}{w['icon']}{w['eta_str']}" for w in windows)

    ctx_nudge, ctx_pct = _ctx_nudge(state, now)
    ctx_part = f"🧠{ctx_pct:.0f}%{'💡' if ctx_nudge else ''}" if ctx_pct is not None else ""

    return "  ".join(p for p in (rate_part, ctx_part) if p)


def _worst_rate_icon(windows):
    """Worst-of-both-windows severity icon (🪫 > ⚡ > 🔋), or 🔋 when
    there's nothing to report yet (no windows at all)."""
    if not windows:
        return "🔋"
    return max((w["icon"] for w in windows), key=lambda i: _ICON_RANK[i])


def pulse_detail():
    """The full bar view, for `/oct-pulse` re-run while already enabled —
    same numbers as the compact statusLine, expanded into the
    center-anchored margin bars (see _battery) instead of just icon +
    duration."""
    state = _load_rl_state()
    updated_at = state.get("updated_at")
    if not updated_at:
        print("還沒有資料，先讓 statusLine 刷新過一次（隨便切一下視窗）再重跑。")
        return
    now = datetime.now(timezone.utc)
    if now - datetime.fromisoformat(updated_at) > timedelta(seconds=_RL_STALE_SECONDS):
        print("資料太舊了（statusLine 超過 30 分鐘沒刷新），先切一下視窗讓它刷新再重跑。")
        return

    windows = _rate_windows(state, now)
    rate_icon = _worst_rate_icon(windows)
    ctx_nudge, ctx_pct = _ctx_nudge(state, now)

    verdict = {
        "🪫": "有窗口燒得比排程快很多，得馬上放慢速度",
        "⚡": "有窗口燒得比排程快，留意一下速度",
        "🔋": "額度都在排程內",
    }[rate_icon]
    if ctx_nudge:
        verdict += "；ctx 偏高，收工前建議 /oct-nap"

    print(f"{rate_icon}{'💡' if ctx_nudge else ''} {verdict}")
    if ctx_pct is not None:
        print(f"ctx:{ctx_pct:.0f}%")
    if windows:
        print("  ".join(f"{w['label']} {w['pct']:.0f}%{w['bar']}" for w in windows))


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


def _current_account_id():
    """Best-effort id for the logged-in Claude account (org first, then
    account), so baselines don't get compared across different
    accounts/orgs sharing this machine — switching accounts changes which
    connectors/policies are attached and the entry fee legitimately differs."""
    try:
        oauth = json.loads((Path.home() / ".claude.json").read_text()).get("oauthAccount", {})
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
    """Passive check for /oct-wake: print one line only when this session's
    entry fee has grown >_ENTRY_FEE_ALERT_PCT vs the stored per-model
    baseline. Silent on first sighting of a model (baseline just gets set),
    silent when within threshold. Fixed anchor, not rolling — stays quiet
    until the user explicitly accepts a new baseline (--entry-fee-accept)."""
    model, fee = _entry_fee_now()
    if model is None:
        return
    key = _entry_fee_key(model)
    baseline = _load_entry_fee_baseline()
    base = baseline.get(key)
    if base is None:
        baseline[key] = fee
        _ENTRY_FEE_FILE.write_text(json.dumps(baseline, indent=2))
        return
    if base <= 0:
        return
    pct = (fee - base) / base * 100
    if pct >= _ENTRY_FEE_ALERT_PCT:
        print(f"💡 入場費從 {fmt_k(base)} 漲到 {fmt_k(fee)}（+{pct:.0f}%），"
              f"可能是新裝了 skill/MCP，要接受新基準嗎？（{model}）")


def entry_fee_accept():
    model, fee = _entry_fee_now()
    if model is None:
        print("目前 session 還沒有任何呼叫，無法設定基準")
        return
    baseline = _load_entry_fee_baseline()
    baseline[_entry_fee_key(model)] = fee
    _ENTRY_FEE_FILE.write_text(json.dumps(baseline, indent=2))
    print(f"✅ 已接受新基準：{model} = {fmt_k(fee)}")


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
                ans = input(f"\n── {i+1}/{total} 筆 ── Enter 繼續 / q 離開: ")
                if ans.strip().lower() == "q":
                    break
            except (EOFError, KeyboardInterrupt):
                print()
                break


_HABIT_LONG_ANSWER_CHARS = 1200   # an answer this long is "a wall" for follow-up purposes
_HABIT_LONG_ANSWER_STEPS = 5      # or this many numbered lines — a step-by-step dump
_HABIT_SHORT_QUESTION_CHARS = 60  # a follow-up this short right after a wall = didn't land
_HABIT_FAT_CTX_TOKENS = 100_000   # cache_read above this: every "好" costs real money
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
    out.append(f"🩺 oct-checkup habits  |  過去 {days} 天，{len(files)} 個 session\n")
    fired = 0

    def ex_line(sid, ts, text):
        return f"      · {sid} {ts[5:16].replace('T', ' ')}  「{_snip(text)}」"

    if wall_then_q:
        fired += 1
        cost = sum(c for c, *_ in wall_then_q)
        out.append(f"1. 長篇回答後馬上回頭問短問題  ×{len(wall_then_q)}  光重讀 context ≈${cost:.2f}")
        out.append("   Claude 一次倒一大段（或 5 步以上），你看到一半就得問。多問的每一句都要重讀整段對話。")
        for c, sid, ts, txt in sorted(wall_then_q, reverse=True)[:_HABIT_MAX_EXAMPLES]:
            out.append(ex_line(sid, ts, txt))
        out.append("   建議規則：操作型流程一次只給一步、標明對象、等回報再給下一步；長結論寫檔只給路徑。\n")

    if fat_chatter:
        fired += 1
        cost = sum(c for c, *_ in fat_chatter)
        out.append(f"2. 對話很胖時還在短往返  ×{len(fat_chatter)}  光重讀 context ≈${cost:.2f}")
        out.append(f"   context 超過 {_HABIT_FAT_CTX_TOKENS // 1000}K 之後，連回一句「好」都要付整段重讀的錢。")
        for c, sid, ts, txt, ctx in sorted(fat_chatter, reverse=True)[:_HABIT_MAX_EXAMPLES]:
            out.append(ex_line(sid, ts, txt) + f"  ctx {fmt_k(ctx)} → ${c:.2f} 只為了讀這句")
        out.append("   建議習慣：ctx 過半就 /oct-nap 然後 /clear，用便條接續，不要拖著胖對話。\n")

    if len(corrections) >= 3:
        fired += 1
        by_sess = {}
        for sid, ts, txt in corrections:
            by_sess.setdefault(sid, []).append((ts, txt))
        out.append(f"3. 反覆糾正 Claude  ×{len(corrections)}，跨 {len(by_sess)} 個 session")
        out.append("   同一種糾正說第二次，就代表它該是一條長期記憶，不是一句話。")
        for sid, ts, txt in corrections[-_HABIT_MAX_EXAMPLES:]:
            out.append(ex_line(sid, ts, txt))
        out.append("   建議：把重複出現的那條糾正存成 feedback 記憶（規則 + 為什麼 + 什麼時候套用）。\n")

    if fat_no_nap:
        fired += 1
        out.append(f"4. 胖 session 結束時沒寫便條  ×{len(fat_no_nap)}")
        out.append(f"   結束時 context 還有 {_HABIT_FAT_SESSION_END // 1000}K+，之後若 --resume 就是整段冷重算。")
        for sid, cr, end in sorted(fat_no_nap, key=lambda x: -x[1])[:_HABIT_MAX_EXAMPLES]:
            out.append(f"      · {sid}  ctx {fmt_k(cr)}  {datetime.fromtimestamp(end).strftime('%m-%d %H:%M')}")
        out.append("   建議習慣：收工前 /oct-nap（或 /oct-sleep），下次 /oct-wake 只讀 1-2k 便條。\n")

    if len(post_compact_corr) >= _HABIT_MIN_POST_COMPACT_CORRECTIONS:
        fired += 1
        by_sess = {}
        for sid, ts, txt, ccount in post_compact_corr:
            by_sess.setdefault(sid, []).append((ts, txt, ccount))
        out.append(f"5. 壓縮後又被糾正一次  ×{len(post_compact_corr)}，跨 {len(by_sess)} 個 session")
        out.append("   auto-compact 剛發生沒多久，就得再糾正一次同類的事——像是規則活在對話裡，"
                    "壓縮一過就被沖淡，不是真的記住了。（這是時間上的巧合偵測，不保證兩者內容相關；"
                    "session 當天 compact 次數越多，巧合撞進來的機率也越高，自己看一下例子、compact 次數偏高的可以多打折扣。）")
        for sid, ts, txt, ccount in post_compact_corr[-_HABIT_MAX_EXAMPLES:]:
            out.append(ex_line(sid, ts, txt) + f"  （該 session 當天 compact {ccount} 次）")
        out.append("   建議：這類規則搬進 CLAUDE.md（全域或該專案自己的），不要只留在對話裡靠它撐過壓縮。\n")

    scan_secs = time.monotonic() - _scan_start
    if scan_secs >= _HABIT_SLOW_SCAN_SEC:
        out.append(f"⏱️ 這次掃描本身花了 {scan_secs:.1f}s（{len(files)} 個 session，{days} 天份）"
                    "——這支工具應該只是輕量本機掃描，這樣偏慢。")
        out.append("   如果常態如此，歡迎回報：https://github.com/sunososobro-hub/claude-octopus/issues"
                    "（附上這行數字就好，不用附任何對話內容）\n")

    if fired == 0:
        out.append(f"✅ 過去 {days} 天沒看到明顯的浪費模式。")
    else:
        out.append("要把哪幾條存成長期記憶？（例：「1 3」/「都要」/「不用」）")
    print("\n".join(out))


def main():
    args = sys.argv[1:]

    if args and args[0] == "--statusline-hook":
        statusline_hook()
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
        # Model name, ctx%, and 5h/7d reset+可撐 are NOT repeated here — all
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
        label = f"最新 {shown} 筆（共 {total_calls} 筆）"
    elif last_n:
        label = f"最新 {shown} 筆"
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
