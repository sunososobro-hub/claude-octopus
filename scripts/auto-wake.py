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
MAX_CHARS = 9000  # overridden by oct_core.CHECKPOINT_CAP below
PRIORITY = (("Task", "\u4efb\u52d9"), ("Next Steps",), ("Decisions",), ("Running agents",), ("Pending dispatch",), ("Awaiting Reply",))

INSTRUCTION = (
    "oct-toolkit auto-wake: user ran /clear; the checkpoint below is their latest /oct-nap. "
    "Reply once with the oct-wake Step 4 confirmation (Woke from <hash>, Task, open Next steps, Decisions / Watch in full), "
    "then continue from it. Do not re-read the file.\n\n"
)

STALE = (
    "BUT the checkpoint is STALE: {n} user turn(s) came after it was taken. The `## Since checkpoint` block at the end is "
    "newer than the checkpoint and wins over it. Before replying, mark every Next steps / Pending dispatch / Awaiting Reply "
    "item that the block answers, dispatches or completes as done ([x], with the user's words); never ask again a question "
    "the user answered there and never re-dispatch what it shows as already sent. Add one `Since checkpoint:` line to the "
    "confirmation saying what changed.{cut}"
)
STALE_CUT = (
    " The block was cut to fit ({k} older lines omitted): tell the user the checkpoint was {n} turns stale and some detail "
    "may be missing; grep {path} for a needed detail, never read it whole."
)

CUTMARK = chr(10) + "[... section cut ...]" + chr(10)

CUT = (
    "oct-toolkit auto-wake: user ran /clear; the checkpoint below is their latest /oct-nap but it was TOO LONG to inject whole "
    "({n} of {total} chars; priority sections first: Task, Next Steps, Decisions / Watch, Running agents, Pending dispatch, "
    "Awaiting Reply, then the rest). Cut or omitted: {cut}. Before the oct-wake Step 4 confirmation, Read {path} for what is "
    "missing (Decisions / Watch must be shown in full), then continue from it.\n\n"
)

CANDIDATES = (
    "oct-toolkit auto-wake: the user just ran /clear, but this window has no checkpoint of its own. The entries below may belong "
    "to another window or project (`*` = working directory matches the project tag). Do NOT load any silently. Show this list "
    "verbatim, ask which to resume (or none), then load the picked one with the /oct-wake <hash> flow:\n\n"
)

MENU = (
    "oct-toolkit auto-wake: the user just ran /clear, but the working directory does not identify the project and "
    "several projects have checkpoints from the last 12h. Do NOT guess or load any. Show this list verbatim, ask which to "
    "resume (or none), then load the picked one with the /oct-wake <hash> flow:\n\n"
)

def enabled():
    try:
        return bool(json.loads((CLAUDE_DIR / "oct-toolkit.json").read_text(encoding="utf-8")).get("auto_wake", True))
    except Exception:
        return True

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import oct_core
    MAX_CHARS = getattr(oct_core, "CHECKPOINT_CAP", MAX_CHARS)
except Exception:
    oct_core = None

WAIT_S = 15

PENDING = (
    "oct-toolkit auto-wake: this window's /oct-nap was still writing when the user ran /clear, so nothing was loaded. "
    "Tell the user in one line to run /oct-wake in a minute (or pick below). Do NOT load any checkpoint yourself.\n\n"
)

def rows_now():
    index = SUMMARIES / "index.md"
    rows = []
    if index.exists():
        for line in index.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 4 and re.fullmatch(r"[0-9a-z]{8}", parts[0]) and (SUMMARIES / f"{parts[0]}.md").exists():
                w = parts[4] if len(parts) >= 5 and parts[4].isdigit() else ""
                rows.append((parts[0], parts[2], parts[1], parts[3], w))
    return rows

def mt(h):
    try:
        return (SUMMARIES / f"{h}.md").stat().st_mtime
    except OSError:
        return 0

def fresh(r):
    return time.time() - mt(r[0]) <= MAX_AGE

def own(rows, win, since=0):
    c = [r for r in rows if win and r[4] == win and mt(r[0]) >= since and fresh(r)]
    return max(c, key=lambda r: mt(r[0])) if c else None

def menu_of(rows):
    best = {}
    for r in sorted(rows, key=lambda r: mt(r[0])):
        best[r[1].lower()] = r
    return sorted(best.values(), key=lambda r: -mt(r[0]))[:5]

def pick(cwd, win="", alive=lambda w: False):
    """Fallback when this window has no checkpoint of its own: never load one silently (it belongs to another
    window or project); offer fresh checkpoints as candidates, cwd matches first."""
    rows = rows_now()
    if win:
        rows = [r for r in rows if not r[4] or r[4] == win or not alive(r[4])]
    rows = [r for r in rows if fresh(r)]
    if not rows:
        return None
    name = Path(cwd).name.lower() if cwd else ""
    mine = {r[0] for r in rows if name and r[1] and (r[1].lower() in cwd.lower() or name in r[1].lower())}
    best = menu_of(rows)
    for r in rows:  # a cwd match always makes the list even if it is not among the 5 newest tags
        if r[0] in mine and all(x[1].lower() != r[1].lower() for x in best):
            best.append(r)
    best.sort(key=lambda r: (r[0] not in mine, -mt(r[0])))
    return "candidates", best[:5], mine

def choose(cwd):
    win = oct_core.window_id() if oct_core else ""
    if not win:
        return pick(cwd)
    marked = oct_core.nap_marked(win)
    r = own(rows_now(), win, marked)
    end = time.time() + WAIT_S
    while not r and marked and time.time() < end:
        time.sleep(1)
        r = own(rows_now(), win, marked)
    if marked:
        oct_core.nap_unmark(win)
    if r:
        return "load", r[0]
    if marked:
        return "pending", menu_of([x for x in rows_now() if fresh(x)])
    r = own(rows_now(), win)
    if r:
        return "load", r[0]
    return pick(cwd, win, oct_core.pid_alive)

def split_sections(text):
    parts = re.split(r"(?m)^(?=## )", text)
    return parts[0], parts[1:]


def priority_rank(sec):
    name = sec[3:].split(chr(10), 1)[0].strip().casefold()
    for i, alts in enumerate(PRIORITY):
        if any(name.startswith(a.casefold()) for a in alts):
            return i
    return len(PRIORITY)


def fit(text, cap=None):
    """-> (text to inject, list of cut/omitted section names). Whole text if it fits; otherwise the header and the
    priority sections first (so Next Steps / Decisions are never the part that gets cut), then the rest in file order."""
    cap = cap or MAX_CHARS
    if len(text) <= cap:
        return text, []
    head, secs = split_sections(text)
    order = sorted(range(len(secs)), key=lambda i: (priority_rank(secs[i]), i))
    used, kept, skipped = min(len(head), cap), {}, []
    for i in order:  # pass 1: whole sections that fit (a small later section may fit after a big one is skipped)
        if len(secs[i]) <= cap - used:
            kept[i] = secs[i]
            used += len(secs[i])
        else:
            skipped.append(i)
    cut = []
    for i in skipped:  # pass 2: partial text of the highest-priority sections that did not fit
        name = secs[i][3:].split(chr(10), 1)[0].strip()
        room = cap - used
        if room > 300:
            k = secs[i].rfind(chr(10), 0, room)
            kept[i] = secs[i][:k if k > 0 else room] + CUTMARK
            used += len(kept[i])
            cut.append(name + " (partial)")
        else:
            cut.append(name)
    return head[:cap] + "".join(kept[i] for i in order if i in kept), cut


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

def since(h, payload):
    """-> (instruction addendum, `## Since checkpoint` block) for turns after the checkpoint; ("", "") if none."""
    try:
        import nap_delta
        got = nap_delta.build(h, payload.get("session_id") or "", payload.get("transcript_path") or "")
    except Exception:
        return "", ""
    if not got:
        return "", ""
    cut = STALE_CUT.format(k=got["omitted"], n=got["turns"], path=got["transcript"]) if got["omitted"] else ""
    return STALE.format(n=got["turns"], cut=cut), "\n\n" + got["text"]


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    if payload.get("source") != "clear" or not enabled():
        return
    got = choose(payload.get("cwd") or os.getcwd())
    if not got:
        return
    if got[0] in ("menu", "pending"):
        menu = "\n".join(f"{i}  {r[0]}  {r[2]}  [{r[1]}]  {r[3]}" for i, r in enumerate(got[1], 1))
        head = MENU if got[0] == "menu" else PENDING
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": head + menu}}))
        return
    h = got[1]
    try:
        with open(CLAUDE_DIR / "oct-toolkit" / "clears.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time()}) + "\n")
    except OSError:
        pass
    full = (SUMMARIES / f"{h}.md").read_text(encoding="utf-8", errors="replace")
    text, cut = fit(full)
    head = INSTRUCTION if not cut else CUT.format(n=len(text), total=len(full), cut=", ".join(cut), path=SUMMARIES / f"{h}.md")
    try:
        (SUMMARIES / ".last_woken").write_text(h + "\n")
    except Exception:
        pass
    stale, delta = since(h, payload)
    if stale:
        head = head.rstrip("\n") + " " + stale + "\n\n"
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": head + text + verify(h) + delta}}))

if __name__ == "__main__":
    main()
