#!/usr/bin/env python3

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
SUMMARIES_DIR = CLAUDE_DIR / "summaries"
LAST_WOKEN_FILE = SUMMARIES_DIR / ".last_woken"
SETTINGS_FILE = CLAUDE_DIR / "settings.json"
PULSE_NUDGED_FILE = CLAUDE_DIR / ".oct-pulse-nudged"

SHIM_FILE = CLAUDE_DIR / "oct-toolkit" / "statusline.py"
SHIM = "import os, subprocess, sys\nt = %r\nsys.exit(subprocess.call([sys.executable, t, '--statusline-hook']) if os.path.isfile(t) else 0)\n"

def write_shim():
    target = str(Path(__file__).resolve().parent / "usage-analyze.py")
    body = SHIM % target
    try:
        if SHIM_FILE.exists() and SHIM_FILE.read_text(encoding="utf-8") == body:
            return
        SHIM_FILE.parent.mkdir(parents=True, exist_ok=True)
        SHIM_FILE.write_text(body, encoding="utf-8")
    except Exception:
        pass

def checkpoint_nudge():
    if not SUMMARIES_DIR.exists():
        return None
    checkpoints = sorted(
        (f for f in SUMMARIES_DIR.glob("*.md") if re.fullmatch(r"[0-9a-f]{8}", f.stem)),
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
    return f"💾 Unresumed checkpoint: {latest_hash} ({date_str}). Type /oct-wake to resume, or /oct-wake --list to see all."

def statusline_wired():
    try:
        settings = json.loads(SETTINGS_FILE.read_text())
    except Exception:
        return False
    cmd = (settings.get("statusLine") or {}).get("command", "")
    return "usage-analyze.py" in cmd or "oct-toolkit/statusline.py" in cmd

def pulse_nudge():
    if PULSE_NUDGED_FILE.exists() or statusline_wired():
        return None
    try:
        PULSE_NUDGED_FILE.parent.mkdir(parents=True, exist_ok=True)
        PULSE_NUDGED_FILE.write_text(datetime.now().isoformat())
    except Exception:
        pass
    return "🐙 oct-toolkit installed. The status bar isn't on yet — run /oct-pulse to enable it. Shown only once."

def auto_wake_on():
    try:
        return bool(json.loads((CLAUDE_DIR / "oct-toolkit.json").read_text(encoding="utf-8")).get("auto_wake", True))
    except Exception:
        return True

def checkup_and_memory(cwd):
    """0.5.3: zero-token first checkup (background script), pending report, memory-bloat nag."""
    out = []
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import oct_core
        oct_core.auto_checkup_start(cwd)
        oct_core.ma_stale_refresh()
        rep = oct_core.pending_report_text()
        if rep:
            out.append(rep)
        nag = oct_core.memory_nag(cwd)
        if nag:
            out.append(nag)
    except Exception:
        pass
    return out

OCT_DIR = CLAUDE_DIR / "oct-toolkit"
BASELINE_FILE = OCT_DIR / "baseline.json"
SAVINGS_FILE = OCT_DIR / "savings.json"
WEEKLY_FILE = OCT_DIR / ".weekly-savings"
ANALYZE = str(Path(__file__).resolve().parent / "usage-analyze.py")

def cfg(key):
    try:
        return bool(json.loads((CLAUDE_DIR / "oct-toolkit.json").read_text(encoding="utf-8")).get(key, True))
    except Exception:
        return True

def spawn_bg(args):
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x08000000 | 0x00000200
    else:
        kw["start_new_session"] = True
    try:
        subprocess.Popen([sys.executable, ANALYZE] + args, **kw)
    except Exception:
        pass

def ensure_baseline():
    try:
        OCT_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(BASELINE_FILE, "x", encoding="utf-8") as f:
                json.dump({"status": "pending", "install_ts": time.time()}, f)
        except FileExistsError:
            if json.loads(BASELINE_FILE.read_text(encoding="utf-8")).get("status") == "done"                     or time.time() - BASELINE_FILE.stat().st_mtime < 600:
                return
            BASELINE_FILE.touch()
        spawn_bg(["--baseline"])
    except Exception:
        pass

def weekly_savings():
    ensure_baseline()
    try:
        fresh = time.time() - SAVINGS_FILE.stat().st_mtime < 1800
    except OSError:
        fresh = False
    if not fresh:
        spawn_bg(["--savings-refresh", "--if-stale"])
    if not cfg("weekly_savings"):
        return None
    wk = datetime.now().strftime("%G-W%V")
    try:
        if WEEKLY_FILE.read_text(encoding="utf-8").strip() == wk:
            return None
    except OSError:
        pass
    try:
        d = json.loads(SAVINGS_FILE.read_text(encoding="utf-8"))
        if time.time() - d["computed_at"] > 14 * 86400:
            return None
        if d["total"] < 0.01:
            w = d.get("why")
            if not w:
                return None
            WEEKLY_FILE.write_text(wk, encoding="utf-8")
            return (
                "oct-toolkit: in your first reply add one short sentence in the user's language: "
                "%s Do not ask for a response." % w["msg"]
            )
        WEEKLY_FILE.write_text(wk, encoding="utf-8")
        return (
            "oct-toolkit: in your first reply add one short sentence in the user's language: "
            "estimated 7-day savings $%.2f (nap/clear $%.2f, %d duplicate reads skipped $%.2f). "
            "Do not ask for a response." % (d["total"], max(0.0, d["nap"]), d["blocks"], d["read"])
        )
    except Exception:
        return None

def main():
    write_shim()
    try:
        payload = json.load(sys.stdin)
        source = payload.get("source", "startup")
        cwd = payload.get("cwd") or os.getcwd()
    except Exception:
        source, cwd = "startup", os.getcwd()
    if source != "startup":
        print("{}")
        return
    msgs = [m for m in (pulse_nudge(), checkpoint_nudge() if auto_wake_on() else None) if m]
    msgs += checkup_and_memory(cwd)
    out = {"systemMessage": "\n".join(msgs)} if msgs else {}
    ask = weekly_savings() or ""
    if ask:
        out["hookSpecificOutput"] = {"hookEventName": "SessionStart", "additionalContext": ask}
    print(json.dumps(out))

if __name__ == "__main__":
    main()
