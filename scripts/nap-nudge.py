#!/usr/bin/env python3

import json
import os
import sys
import time
from pathlib import Path

CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
SUMMARIES = CLAUDE_DIR / "summaries"
STATE = CLAUDE_DIR / ".oct-nudge-state.json"
LOG = CLAUDE_DIR / "oct-toolkit" / "nudges.jsonl"
FIRST = 30
EVERY = 15
GROWTH = 80000
REMIND_AFTER = 5

NAP = (
    "oct-toolkit: {why}. Without pausing your reply, run the /oct-nap background procedure now "
    "(fork per oct-nap.md; foreground only if unavailable), then continue the request."
)
REMIND = (
    "oct-toolkit: checkpoint saved {k} turns ago. Tell the user once, in one short line, "
    "they can /clear anytime and it resumes automatically. Do not repeat."
)

def cfg(key, default=True):
    try:
        v = json.loads((CLAUDE_DIR / "oct-toolkit.json").read_text(encoding="utf-8")).get(key, default)
        if isinstance(default, bool):
            return bool(v)
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else default
    except Exception:
        return default

def scan(path):
    n = 0
    usage = None
    first = None
    ids = set()
    with open(path, "rb") as f:
        for line in f:
            if b'"isSidechain":true' in line:
                continue
            if b'"type":"user"' in line and b'"tool_result"' not in line and b'"isMeta":true' not in line:
                n += 1
            elif b'"type":"assistant"' in line and b'"usage"' in line:
                try:
                    m = json.loads(line).get("message") or {}
                    if m.get("usage"):
                        ids.add(m.get("id") or len(ids))
                        usage = m["usage"]
                        if first is None:
                            first = (usage, m.get("model") or "")
                except Exception:
                    pass
    return n, usage, first, len(ids)

def total(usage):
    return sum(usage.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))

def baseline(first):
    usage, model = first
    try:
        cj = CLAUDE_DIR / ".claude.json" if os.environ.get("CLAUDE_CONFIG_DIR") else Path.home() / ".claude.json"
        oa = json.loads(cj.read_text(encoding="utf-8")).get("oauthAccount", {})
        key = f"{oa.get('organizationUuid') or oa.get('accountUuid') or 'unknown'}:{model}"
        fee = json.loads((CLAUDE_DIR / "scripts" / "entry-fee-baseline.json").read_text(encoding="utf-8")).get(key)
        if isinstance(fee, (int, float)) and fee > 0:
            return fee
    except Exception:
        pass
    return total(usage)

def latest_cp():
    try:
        return max((f.stat().st_mtime for f in SUMMARIES.glob("*.md") if f.name != "index.md"), default=0)
    except OSError:
        return 0

def load():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save(all_state, sid, st):
    all_state[sid] = st
    if len(all_state) > 20:
        for k in list(all_state)[:-20]:
            del all_state[k]
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(all_state))
    except OSError:
        pass

def log_nudge():
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time()}) + "\n")
    except OSError:
        pass

def dynamic(first, usage, calls):
    """Net-saving verdict from the user's rolling baseline, or None when it cannot be judged."""
    if not (first and usage and cfg("nudge_dynamic")):
        return None
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import oct_core
        if not oct_core.cfg("nudge_dynamic"):
            return None
        b, ma = oct_core.model_baseline(first[1])
        if not b:
            return None
        r = oct_core.net_saving(b, total(usage), calls, ma.get("ck", oct_core.CK_DEFAULT))
        r["min"] = oct_core.cfg("nudge_min_net_usd")
        r["explicit"] = oct_core.cfg_has("nudge_growth_tokens")
        return r
    except Exception:
        return None

def decide(st, n, grown, cp, dyn=None):
    out = None
    if st.get("cp") is None:
        st["cp"] = cp
    elif cp > st["cp"]:
        st.update(cp=cp, base=n, last=n, reminded=False, napped=True)
    base = st.get("base", 0)
    if st.get("napped") and not st.get("reminded") and cfg("clear_reminder") and n - base >= REMIND_AFTER:
        st["reminded"] = True
        return REMIND.format(k=n - base)
    if st.get("napped") or not cfg("nap_nudge"):
        return None
    last = st.get("last")
    why = None
    if dyn:
        if dyn["net"] > dyn["min"]:
            why = (f"a nap and /clear now would net about ${dyn['net']:.2f} after the ~${dyn['cold']:.2f} cold start "
                   f"(your own history, ~{dyn['H']:.0f} calls expected to remain)")
        if dyn["explicit"] and grown >= cfg("nudge_growth_tokens", GROWTH):
            why = f"context has grown ~{round(grown / 1000)}k tokens since session start"
    else:
        if n - base >= FIRST:
            why = f"this session has {n - base} user turns"
        if grown >= cfg("nudge_growth_tokens", GROWTH):
            why = f"context has grown ~{round(grown / 1000)}k tokens since session start"
    if why and (last is None or n - last >= EVERY):
        st["last"] = n
        log_nudge()
        out = NAP.format(why=why)
    return out

def main():
    try:
        payload = json.load(sys.stdin)
        path = payload["transcript_path"]
    except Exception:
        return
    try:
        n, usage, first, calls = scan(path)
    except OSError:
        return
    n += 1
    grown = max(0, total(usage) - baseline(first)) if usage and first else 0
    sid = payload.get("session_id") or "unknown"
    all_state = load()
    st = all_state.get(sid, {})
    msg = decide(st, n, grown, latest_cp(), dynamic(first, usage, calls))
    save(all_state, sid, st)
    if msg:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": msg}}))

if __name__ == "__main__":
    main()
