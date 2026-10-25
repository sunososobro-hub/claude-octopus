#!/usr/bin/env python3
import glob
import io
import json
import os
import re
import sys

CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
PROJ = os.path.join(CLAUDE_DIR, "projects")
TAG = re.compile(r"^\s*<([a-zA-Z_-]+)[^>]*>.*?</\1>\s*", re.S)
ITEM = r"(?:\d+[.)]|[①-⑨])"


def text(c):
    if isinstance(c, list):
        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
    return (c or "").strip()


def human_text(d):
    if d.get("type") != "user" or d.get("isMeta") or d.get("isSidechain"):
        return ""
    kind = (d.get("origin") or {}).get("kind")
    if kind and kind != "human":
        return ""
    c = text((d.get("message") or {}).get("content"))
    while TAG.match(c):
        c = TAG.sub("", c, count=1)
    if not c or c.startswith(("<", "Another Claude", "Caveat")):
        return ""
    return c


def has_human(fn):
    try:
        for line in io.open(fn, encoding="utf8", errors="replace"):
            if '"user"' not in line:
                continue
            try:
                if human_text(json.loads(line)):
                    return True
            except Exception:
                continue
    except OSError:
        pass
    return False


def arg(a, flag):
    # value after flag; "" when flag is last (e.g. --session ${CLAUDE_SESSION_ID} expanded empty)
    i = a.index(flag) + 1 if flag in a else len(a)
    return a[i] if i < len(a) else ""


def pick():
    a = sys.argv[1:]
    if arg(a, "--transcript"):
        return arg(a, "--transcript")
    sid = arg(a, "--session") or os.environ.get("CLAUDE_SESSION_ID", "")
    if sid and not sid.startswith("$"):
        hit = glob.glob(os.path.join(PROJ, "*", sid + ".jsonl"))
        if hit:
            return hit[0]
    fs = sorted(glob.glob(os.path.join(PROJ, "*", "*.jsonl")), key=os.path.getmtime, reverse=True)
    here = re.sub(r"[^A-Za-z0-9]", "-", os.getcwd()).lower()
    fs.sort(key=lambda f: os.path.basename(os.path.dirname(f)).lower() != here)
    for fn in fs[:40]:
        if has_human(fn):
            return fn
    return fs[0] if fs else None


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    fn = pick()
    users, lists = [], []
    for line in (io.open(fn, encoding="utf8", errors="replace") if fn else []):
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("type") == "user":
            c = human_text(d)
            if c:
                users.append(c.replace("\n", " "))
        elif d.get("type") == "assistant" and not d.get("isSidechain"):
            c = text((d.get("message") or {}).get("content"))
            if len(re.findall(r"^\s*" + ITEM, c, re.M)) >= 3:
                heads = re.findall(r"^\s*(?:[-*]\s*)?(" + ITEM + r".{0,40})", c, re.M)
                lists.append(" | ".join(h.strip() for h in heads))
    print("\n## User quotes index")
    print("### Recent user messages")
    for u in users[-15:]:
        print("- " + u[:120])
    if not users:
        print("- Extraction empty (transcript: %s)" % (fn or "none"))
    print("### Numbered lists I proposed")
    for x in lists[-3:]:
        print("- " + x[:300])


if __name__ == "__main__":
    main()
