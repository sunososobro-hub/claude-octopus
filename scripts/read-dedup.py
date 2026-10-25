#!/usr/bin/env python3

import json
import os
import sys
import tempfile
import time
from pathlib import Path

_CACHE_DIR = Path(tempfile.gettempdir())
_MAX_AGE = 86400

def prune():
    cutoff = time.time() - _MAX_AGE
    try:
        for f in _CACHE_DIR.glob("oct-read-cache-*.json"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError:
                pass
    except OSError:
        pass

def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path")
    if not file_path:
        sys.exit(0)

    try:
        st = os.stat(file_path)
    except OSError:
        sys.exit(0)

    session_id = payload.get("session_id") or os.environ.get("CLAUDE_SESSION_ID", "unknown")
    cache_file = _CACHE_DIR / f"oct-read-cache-{session_id}.json"

    prune()
    cache = {}
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
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
            f"This file ({file_path}, same offset/limit) was already read in this session, "
            "and it is unchanged (same mtime/size). No need to re-read; use the earlier read result.",
            file=sys.stderr,
        )
        try:
            d = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "oct-toolkit"
            d.mkdir(parents=True, exist_ok=True)
            lim = tool_input.get("limit")
            size = min(st.st_size, int(lim) * 80) if isinstance(lim, int) and lim > 0 else st.st_size
            size = min(size, 100000)
            with open(d / "read-blocks.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": int(time.time()), "b": size}) + "\n")
        except Exception:
            pass
        sys.exit(2)

    cache[key] = fingerprint
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cache), encoding="utf-8")
    except Exception:
        pass
    sys.exit(0)

if __name__ == "__main__":
    main()
