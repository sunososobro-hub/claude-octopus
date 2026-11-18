#!/usr/bin/env python3
"""PreToolUse hook: mechanical brake for sub-agents.

Measures the live sub-agent transcript (tool-call steps and context size) and,
once either limit is passed, denies the next tool call with a hand-back order.
Does nothing in the main session or when the sub-agent transcript is not found.
Limits: OCT_BRAKE_STEPS (default 25), OCT_BRAKE_TOKENS (default 60000).
"""
import json
import os
import sys

STEPS = 25
TOKENS = 60000


def _limit(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def find_transcript(payload):
    for key in ("agent_transcript_path", "subagent_transcript_path"):
        p = payload.get(key)
        if isinstance(p, str) and os.path.isfile(p):
            return p
    agent_id, main = payload.get("agent_id"), payload.get("transcript_path")
    if agent_id and isinstance(main, str) and main.endswith(".jsonl"):
        for name in ("agent-%s.jsonl" % agent_id, "%s.jsonl" % agent_id):
            p = os.path.join(main[:-6], "subagents", name)
            if os.path.isfile(p):
                return p
    return None


def measure(path):
    """Return (steps, context_tokens) from a transcript file."""
    steps, tokens = 0, 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                msg = (json.loads(line) or {}).get("message") or {}
            except Exception:
                continue
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content")
            if isinstance(content, list):
                steps += sum(1 for b in content if isinstance(b, dict) and b.get("type") == "tool_use")
            u = msg.get("usage") or {}
            t = sum(int(u.get(k) or 0) for k in
                    ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            if t:
                tokens = t  # the latest turn's prompt size is the live context
    return steps, tokens


def build(payload, max_steps=None, max_tokens=None):
    if not payload.get("agent_id"):
        return None
    path = find_transcript(payload)
    if not path:
        return None
    max_steps = max_steps or _limit("OCT_BRAKE_STEPS", STEPS)
    max_tokens = max_tokens or _limit("OCT_BRAKE_TOKENS", TOKENS)
    try:
        steps, tokens = measure(path)
    except OSError:
        return None
    if steps < max_steps and tokens < max_tokens:
        return None
    reason = ("agent-brake: %d steps, ~%dk tokens of context (limits %d steps, %dk tokens). "
              "Stop now. Do not call more tools; reply with what is done and the exact next step."
              % (steps, tokens // 1000, max_steps, max_tokens // 1000))
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def main():
    try:
        payload = json.load(sys.stdin)
        res = build(payload)
    except Exception:
        return 0
    if res:
        print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
