#!/usr/bin/env python3
"""PreToolUse hook (matcher: Read). Blocks re-reading a file this session
when it's byte-for-byte the same call as before — same path, same mtime,
same size, same offset/limit — so the model doesn't pay input tokens twice
for content already sitting in its own context.

Deliberately conservative: keyed by (path, mtime, size, offset, limit), all
scoped to the current session only. A changed mtime (edit, external write)
or a different offset/limit always allows the read through. No claim about
file content survives across sessions — that risk (stale memory serving
wrong content) is exactly what this avoids."""

import json
import os
import sys
from pathlib import Path

_CACHE_DIR = Path("/tmp")


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # can't parse -> don't block

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path")
    if not file_path:
        sys.exit(0)

    try:
        st = os.stat(file_path)
    except OSError:
        sys.exit(0)  # let the real Read tool report the error

    # Prefer session_id from the hook payload itself (confirmed present via
    # a raw payload dump — CLAUDE_SESSION_ID is NOT reliably set in this
    # hook's env, which was silently pooling all sessions into one
    # "unknown" cache file before this fix) over the env var fallback.
    session_id = payload.get("session_id") or os.environ.get("CLAUDE_SESSION_ID", "unknown")
    cache_file = _CACHE_DIR / f"oct-read-cache-{session_id}.json"

    cache = {}
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text())
        except Exception:
            cache = {}

    key = json.dumps([
        file_path,
        tool_input.get("offset"),
        tool_input.get("limit"),
    ])
    fingerprint = [st.st_mtime, st.st_size]

    if cache.get(key) == fingerprint:
        print(
            f"此檔案（{file_path}，同樣的 offset/limit）本次對話已經讀過，"
            "內容未變更（mtime/size 相同）——不需要重讀，請直接參考稍早的讀取結果。",
            file=sys.stderr,
        )
        sys.exit(2)

    cache[key] = fingerprint
    try:
        cache_file.write_text(json.dumps(cache))
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
