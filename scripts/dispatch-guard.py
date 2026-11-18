#!/usr/bin/env python3
"""PreToolUse(Agent) hook: append hand-back rules to every sub-agent brief.

Agents must not poll CI inside a session (each poll resends the whole context).
The rule text is appended to the brief through updatedInput; briefs that ask the
agent to wait for CI are flagged in the hook's additional context as well.
"""
import json
import re
import sys

WAIT_RE = re.compile(r"(?i)(wait(ing)?\s+(for\s+)?(ci|checks?|the\s+run|green)|ci\s+green|poll\w*\s+ci|gh\s+run\s+watch|等\s*ci|ci\s*綠|等待?\s*ci)")
RULES = (
    "\n\n[dispatch-guard rules]\n"
    "- Never wait for CI or any other long external job inside this session. After pushing, "
    "hand back at once with the run id and the exact next command; the main window waits in a "
    "background shell and dispatches a short agent to finish (e.g. merge).\n"
    "- Never poll in a loop. Stay within 25 steps and read at most 4 images; screenshot "
    "verification belongs to a separate short agent.\n"
    "- Brake on size as well as time: if your context passes about 60k tokens or you reach "
    "25 steps, whichever comes first, stop and hand back what is done and the exact next step."
)


def build(payload):
    ti = payload.get("tool_input") or {}
    prompt = ti.get("prompt")
    if not isinstance(prompt, str) or prompt.endswith(RULES):
        return None
    out = {"hookEventName": "PreToolUse", "permissionDecision": "allow",
           "updatedInput": dict(ti, prompt=prompt + RULES)}
    if WAIT_RE.search(prompt):
        out["additionalContext"] = ("dispatch-guard: the brief asks the agent to wait for CI; hand-back rules "
                                    "were appended. Prefer a background shell wait in the main window.")
    return {"hookSpecificOutput": out}


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    res = build(payload)
    if res:
        print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
