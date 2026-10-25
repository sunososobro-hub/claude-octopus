#!/usr/bin/env python3

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
SUMMARIES = CLAUDE_DIR / "summaries"
MAX_AGE = 12 * 3600
MAX_CHARS = 9000

INSTRUCTION = (
    "oct-toolkit auto-wake: the user just ran /clear. The checkpoint below is their latest /oct-nap for this project. "
    "Reply once with the oct-wake Step 4 confirmation (Woke from <hash>, Task, still-open Next steps, Decisions / Watch in full), "
    "then continue from it. Do not re-read the file.\n\n"
)

def enabled():
    try:
        return bool(json.loads((CLAUDE_DIR / "oct-toolkit.json").read_text(encoding="utf-8")).get("auto_wake", True))
    except Exception:
        return True

def pick(cwd):
    index = SUMMARIES / "index.md"
    rows = []
    if index.exists():
        for line in index.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3 and re.fullmatch(r"[0-9a-f]{8}", parts[0]) and (SUMMARIES / f"{parts[0]}.md").exists():
                rows.append((parts[0], parts[2].lower()))
    if not rows:
        return None
    name = Path(cwd).name.lower() if cwd else ""
    mt = lambda h: (SUMMARIES / f"{h}.md").stat().st_mtime
    mine = [r for r in rows if name and r[1] and (r[1] in cwd.lower() or name in r[1])]
    h = max((r[0] for r in (mine or rows)), key=mt)
    return h if time.time() - mt(h) <= MAX_AGE else None

def verify(h):
    try:
        text = (SUMMARIES / f"{h}.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if not re.search(r"(?im)^## (Running agents|Pending dispatch)", text):
        return ""
    try:
        r = subprocess.run([sys.executable, str(Path(__file__).with_name("nap_verify.py")), str(SUMMARIES / f"{h}.md")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        out = r.stdout.strip()
        return "\n\n" + out if out else ""
    except Exception:
        return ""

def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    if payload.get("source") != "clear" or not enabled():
        return
    h = pick(payload.get("cwd") or os.getcwd())
    if not h:
        return
    try:
        with open(CLAUDE_DIR / "oct-toolkit" / "clears.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time()}) + "\n")
    except OSError:
        pass
    text = (SUMMARIES / f"{h}.md").read_text(encoding="utf-8", errors="replace")[:MAX_CHARS]
    try:
        (SUMMARIES / ".last_woken").write_text(h + "\n")
    except Exception:
        pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": INSTRUCTION + text + verify(h)}}))

if __name__ == "__main__":
    main()
