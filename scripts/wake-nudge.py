#!/usr/bin/env python3
"""SessionStart hook: two cheap nudges, file checks only, no content reads.
1. An /oct-nap checkpoint exists that /oct-wake hasn't picked up yet.
2. First run only: the status bar (statusLine) isn't wired — the one
   piece a plugin can't install for you — so say so once and point at
   /oct-pulse, instead of letting a new user wonder why the bar in the
   README never showed up."""

import json
from datetime import datetime
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
SUMMARIES_DIR = CLAUDE_DIR / "summaries"
LAST_WOKEN_FILE = SUMMARIES_DIR / ".last_woken"
SETTINGS_FILE = CLAUDE_DIR / "settings.json"
PULSE_NUDGED_FILE = CLAUDE_DIR / ".oct-pulse-nudged"


def checkpoint_nudge():
    if not SUMMARIES_DIR.exists():
        return None
    checkpoints = sorted(
        SUMMARIES_DIR.glob("*.md"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not checkpoints:
        return None
    latest = checkpoints[0]
    latest_hash = latest.stem
    last_woken = ""
    if LAST_WOKEN_FILE.exists():
        try:
            last_woken = LAST_WOKEN_FILE.read_text().strip()
        except Exception:
            pass
    if latest_hash == last_woken:
        return None
    date_str = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    return f"💾 有未接續的進度檢查點：{latest_hash}（{date_str}）。輸入 /oct-wake 接續，或 /oct-wake --list 看全部。"


def statusline_wired():
    try:
        settings = json.loads(SETTINGS_FILE.read_text())
    except Exception:
        return False
    cmd = (settings.get("statusLine") or {}).get("command", "")
    return "usage-analyze.py" in cmd


def pulse_nudge():
    if PULSE_NUDGED_FILE.exists() or statusline_wired():
        return None
    try:
        PULSE_NUDGED_FILE.parent.mkdir(parents=True, exist_ok=True)
        PULSE_NUDGED_FILE.write_text(datetime.now().isoformat())
    except Exception:
        pass
    return "🐙 oct-toolkit 已安裝。底部狀態列（模型 / ctx% / 5h・7d 額度）還沒開——輸入 /oct-pulse 一鍵開啟。只提醒這一次。"


def main():
    msgs = [m for m in (pulse_nudge(), checkpoint_nudge()) if m]
    print(json.dumps({"systemMessage": "\n".join(msgs)} if msgs else {}))


if __name__ == "__main__":
    main()
