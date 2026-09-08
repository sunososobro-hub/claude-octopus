#!/usr/bin/env python3
"""SessionStart hook: cheap nudge if there's an /oct-save checkpoint that
hasn't been picked up by /oct-wake yet. File-existence/mtime check only —
never reads checkpoint content, so this costs ~nothing."""

import json
from datetime import datetime
from pathlib import Path

SUMMARIES_DIR = Path.home() / ".claude" / "summaries"
LAST_WOKEN_FILE = SUMMARIES_DIR / ".last_woken"


def main():
    if not SUMMARIES_DIR.exists():
        print(json.dumps({}))
        return

    checkpoints = sorted(
        SUMMARIES_DIR.glob("*.md"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not checkpoints:
        print(json.dumps({}))
        return

    latest = checkpoints[0]
    latest_hash = latest.stem

    last_woken = ""
    if LAST_WOKEN_FILE.exists():
        try:
            last_woken = LAST_WOKEN_FILE.read_text().strip()
        except Exception:
            pass

    if latest_hash == last_woken:
        print(json.dumps({}))
        return

    date_str = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    msg = f"💾 有未接續的進度檢查點：{latest_hash}（{date_str}）。輸入 /oct-wake 接續，或 /oct-wake --list 看全部。"
    print(json.dumps({"systemMessage": msg}))


if __name__ == "__main__":
    main()
