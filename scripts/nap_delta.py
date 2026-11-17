#!/usr/bin/env python3
"""What happened after a checkpoint was taken.

A checkpoint is a snapshot from the moment the nap started (the background fork sees nothing later). This reads the
tail of that session's transcript and returns a short, redacted `## Since checkpoint` block: user turns, dispatches,
deploy-like commands and the last assistant line of each turn, plus the open checkpoint items a later user turn
answered. Used by auto-wake.py after /clear and by /oct-wake:

    nap_delta.py <hash> [--session <current session id>] [--transcript <current transcript path>]

Prints nothing when the checkpoint is current.
"""
import glob
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nap_extract  # noqa: E402

CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
SUM = os.path.join(CLAUDE_DIR, "summaries")
PROJ = os.path.join(CLAUDE_DIR, "projects")
CAP = 2400            # chars of event lines (about 1k tokens with CJK text)
QUOTA = {"user": 1400, "sent": 400, "ran": 200, "assistant": 400}
WIDTH = {"user": 200, "sent": 110, "ran": 110, "assistant": 140}
ORDER = ("user", "sent", "ran", "assistant")
MAX_ANSWERED = 5
NAP_WINDOW = 900      # a nap that started this long before the file was written still counts as this nap
SCAN_FILES = 12
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
ACTION = re.compile(r"(?i)\b(gh\s+pr\s+(merge|create)|gh\s+release|git\s+push|deploy|npm\s+publish|gh\s+workflow\s+run)\b")
DISPATCH = ("Agent", "Task", "SendMessage")

REDACTED = "[redacted]"
SECRETS = [re.compile(p) for p in (
    r"AIza[0-9A-Za-z_\-]{10,}",                       # Google API keys
    r"AQ\.[0-9A-Za-z_\-.]{10,}",                      # Google OAuth-style tokens
    r"ya29\.[0-9A-Za-z_\-.]{10,}",
    r"\bsk-[0-9A-Za-z_\-]{16,}",
    r"\b(?:ghp|gho|ghu|ghs|ghr)_[0-9A-Za-z]{20,}",
    r"\bgithub_pat_[0-9A-Za-z_]{20,}",
    r"\bxox[abprs]-[0-9A-Za-z\-]{10,}",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\beyJ[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{5,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)",
)]
ASSIGN = re.compile(r"(?i)\b([\w.\-]*(?:api[_-]?key|token|secret|passw(?:or)?d|credential)[\w.\-]*)(\s*[=:]\s*)(\"?)[^\s\"']{6,}")
BEARER = re.compile(r"(?i)\b(bearer\s+)[0-9A-Za-z_\-.=+/]{12,}")
LONG = re.compile(r"(?<![0-9A-Za-z_\-])[0-9A-Za-z_\-]{32,}(?![0-9A-Za-z_\-])")


def redact(s):
    for rx in SECRETS:
        s = rx.sub(REDACTED, s)
    s = ASSIGN.sub(lambda m: m.group(1) + m.group(2) + REDACTED, s)
    s = BEARER.sub(lambda m: m.group(1) + REDACTED, s)

    def long_token(m):  # long mixed-case strings with digits look like keys; hex ids and words do not
        t = m.group(0)
        return REDACTED if re.search(r"[a-z]", t) and re.search(r"[A-Z]", t) and re.search(r"\d", t) else t
    return LONG.sub(long_token, s)


def ts_of(d):
    v = d.get("timestamp")
    if not isinstance(v, str):
        return 0
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
    except ValueError:
        return 0


def one_line(s, width):
    s = " ".join(s.split())
    return s if len(s) <= width else s[:width - 1].rstrip() + "\u2026"


def entries(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if isinstance(d, dict) and d.get("type") in ("user", "assistant") and not d.get("isSidechain"):
                    yield d
    except OSError:
        return


def blocks(d):
    c = (d.get("message") or {}).get("content")
    return [x for x in c if isinstance(x, dict)] if isinstance(c, list) else []


def is_nap_start(b):
    """The tool call that starts a nap: the background fork, or the skill itself (foreground nap)."""
    if b.get("type") != "tool_use":
        return False
    inp = json.dumps(b.get("input") or {}, ensure_ascii=False)
    return (b.get("name") in ("Agent", "Task") and "oct-nap" in inp) or (b.get("name") == "Skill" and "oct-nap" in inp)


def index_row(h):
    """-> (session id, written-at upper bound from the index date) for a checkpoint hash."""
    sess, when = "", 0
    try:
        with open(os.path.join(SUM, "index.md"), encoding="utf-8", errors="replace") as f:
            for line in f:
                c = [x.strip() for x in line.split("|")]
                if len(c) >= 4 and c[0] == h:
                    if UUID.match(c[-1]):
                        sess = c[-1]
                    try:
                        when = time.mktime(time.strptime(c[1], "%Y-%m-%d %H:%M")) + 60
                    except ValueError:
                        pass
    except OSError:
        pass
    return sess, when


def written_at(h):
    """When the checkpoint text was written: file mtime, or the index time if the file was touched later."""
    try:
        t = os.path.getmtime(os.path.join(SUM, h + ".md"))
    except OSError:
        return 0
    when = index_row(h)[1]
    return min(t, when) if when else t


def find_transcript(h, cur_session="", cur_transcript=""):
    """The transcript of the session that wrote checkpoint h (never the current one)."""
    sess = index_row(h)[0]
    if sess:
        if sess == cur_session:
            return ""  # same session: those turns are still in context
        hit = glob.glob(os.path.join(PROJ, "*", sess + ".jsonl"))
        if hit:
            return hit[0]
    dirs = [os.path.dirname(cur_transcript)] if cur_transcript else []
    if not dirs:
        return ""
    skip = {os.path.normcase(os.path.abspath(cur_transcript))}
    if cur_session:
        skip.add(os.path.normcase(os.path.abspath(os.path.join(dirs[0], cur_session + ".jsonl"))))
    fs = [f for f in glob.glob(os.path.join(dirs[0], "*.jsonl")) if os.path.normcase(os.path.abspath(f)) not in skip]
    fs.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    needle = h.encode()
    for fn in fs[:SCAN_FILES]:  # the nap prints "Resume: /oct-wake <hash>" into the session that wrote it
        try:
            with open(fn, "rb") as f:
                if needle in f.read():
                    return fn
        except OSError:
            continue
    return ""


def cutoff(path, written):
    """Snapshot time: the latest nap start within NAP_WINDOW before the file was written, else the write time."""
    best = 0
    for d in entries(path):
        t = ts_of(d)
        if d.get("type") == "assistant" and written - NAP_WINDOW <= t <= written + 5 and any(is_nap_start(b) for b in blocks(d)):
            best = max(best, t)
    return best or written


def events(path, since):
    """-> [(ts, kind, text)] after `since`; kinds: user, sent (dispatch), ran (deploy-like command), assistant."""
    out, last_say = [], None
    for d in entries(path):
        t = ts_of(d)
        if t <= since:
            continue
        if d.get("type") == "user":
            c = (d.get("message") or {}).get("content")
            if isinstance(c, list) and any(isinstance(x, dict) and x.get("type") == "tool_result" for x in c):
                continue
            if last_say:
                out.append(last_say)
                last_say = None
            u = nap_extract.human_text(d)
            if u and not re.match(r"\s*/(oct-toolkit:)?oct-(nap|wake)\b", u):
                out.append((t, "user", u))
            continue
        for b in blocks(d):
            if b.get("type") == "text":
                s = (b.get("text") or "").strip()
                if s and "Resume: /oct-wake" not in s and "napping in background" not in s:
                    last_say = (t, "assistant", next((x for x in s.splitlines() if x.strip()), s))
            elif b.get("type") == "tool_use" and not is_nap_start(b):
                inp = b.get("input") or {}
                if b.get("name") in DISPATCH:
                    what = inp.get("description") or inp.get("summary") or inp.get("to") or ""
                    extra = inp.get("model") or (("to " + str(inp.get("to"))) if b.get("name") == "SendMessage" and inp.get("to") else "")
                    out.append((t, "sent", "%s: %s%s" % (b.get("name"), what, " (%s)" % extra if extra else "")))
                elif b.get("name") in ("Bash", "PowerShell") and ACTION.search(str(inp.get("command") or "")):
                    out.append((t, "ran", str(inp.get("description") or inp.get("command"))))
    if last_say:
        out.append(last_say)
    return [(t, k, one_line(redact(s), WIDTH[k])) for t, k, s in out]


def fit(evs, cap=CAP):
    """Keep the newest lines of each kind within its quota, then spend what is left by priority. -> (kept, omitted)."""
    keep, used = set(), 0
    lines = [len(s) + 16 for _, _, s in evs]
    for strict in (True, False):
        for kind in ORDER:
            spent = sum(lines[i] for i in keep if evs[i][1] == kind)
            for i in range(len(evs) - 1, -1, -1):
                if evs[i][1] != kind or i in keep:
                    continue
                if used + lines[i] > cap or (strict and spent + lines[i] > QUOTA[kind]):
                    break
                keep.add(i)
                used += lines[i]
                spent += lines[i]
    return [evs[i] for i in sorted(keep)], len(evs) - len(keep)


# ---------- which open checkpoint items a later user turn answered ----------
# non-ASCII below: corner brackets, fullwidth colon, arrow, ideographic full stop (repo is English-only)
WAIT_SECTIONS = ("next steps", "pending dispatch", "awaiting reply")
QUOTED = re.compile(r"\u300c([^\u300d]{1,12})\u300d")
ASKED = re.compile(r"(?i)(?:answers?|says?|said|repl(?:y|ies)|words?)\s*[::]?\s*([^\s\u2192,.;\u3002()]+(?:\s*/\s*[^\s\u2192,.;\u3002()]+)*)")
STOP = {"pending", "then", "that", "this", "it", "so", "to", "the", "a", "an", "is", "in", "on", "if", "or", "and"}


def open_items(text):
    out, sec = [], ""
    for line in text.splitlines():
        if line.startswith("## "):
            sec = line[3:].strip().casefold()
            continue
        if not any(sec.startswith(w) for w in WAIT_SECTIONS):
            continue
        m = re.match(r"\s*[-*+]\s+(?:\[([ xX-])\]\s*)?(.*\S)", line)
        if m and (m.group(1) or " ") == " ":
            out.append(m.group(2))
    return out


def choice_words(item):
    """Words the item is waiting to hear from the user: corner-bracket quoted ones and those after answer / says."""
    words = [w.strip() for w in QUOTED.findall(item)]
    for m in ASKED.finditer(item):
        words += [w.strip(" \u300c\u300d\"'`*") for w in m.group(1).split("/")]
    return [w for w in dict.fromkeys(words) if w and w.casefold() not in STOP and (len(w) > 1 or not w.isascii())]


def said_word(word, msg):
    if word.isascii():
        return re.search(r"(?i)(?<![0-9A-Za-z])%s(?![0-9A-Za-z])" % re.escape(word), msg) is not None
    return word in msg


def answered(cp_text, evs):
    users = [(t, s) for t, k, s in evs if k == "user"]
    out = []
    for item in open_items(cp_text):
        words = choice_words(item)
        hit = next(((t, s) for t, s in users if any(said_word(w, s) for w in words)), None)
        if hit:
            out.append("- [x] %s <- answered after the checkpoint, user %s: \"%s\"" % (
                one_line(redact(item), 160), time.strftime("%H:%M", time.localtime(hit[0])), one_line(hit[1], 80)))
    return out[:MAX_ANSWERED]


def build(h, cur_session="", cur_transcript=""):
    """-> {"text", "turns", "omitted", "transcript"} or None when nothing came after the checkpoint."""
    written = written_at(h)
    if not written:
        return None
    path = find_transcript(h, cur_session, cur_transcript)
    if not path:
        return None
    since = cutoff(path, written)
    evs = events(path, since)
    turns = sum(1 for e in evs if e[1] == "user")
    if not evs:
        return None
    try:
        with open(os.path.join(SUM, h + ".md"), encoding="utf-8", errors="replace") as f:
            done = answered(f.read(), evs)
    except OSError:
        done = []
    kept, omitted = fit(evs)
    label = {"user": "user", "sent": "sent", "ran": "ran", "assistant": "assistant"}
    lines = ["## Since checkpoint (%d user turn%s after %s; newer than the checkpoint above and wins over it)" % (
        turns, "" if turns == 1 else "s", time.strftime("%H:%M", time.localtime(since)))]
    if done:
        lines += ["Answered since (treat as done, do not ask again; reopen only if the words do not answer it):"] + done
    if omitted:
        lines.append("(%d older line%s omitted to stay short)" % (omitted, "" if omitted == 1 else "s"))
    lines += ["%s %s: %s" % (time.strftime("%H:%M", time.localtime(t)), label[k], s) for t, k, s in kept]
    return {"text": "\n".join(lines), "turns": turns, "omitted": omitted, "transcript": path}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    if not a or a[0].startswith("-"):
        print(__doc__.strip())
        return 2
    sid = nap_extract.arg(a, "--session")
    got = build(a[0], "" if sid.startswith("$") else sid, nap_extract.arg(a, "--transcript"))
    if got:
        print(got["text"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
