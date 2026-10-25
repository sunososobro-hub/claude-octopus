#!/usr/bin/env python3
import fnmatch
import glob
import json
import os
import re
import shlex
import subprocess
import sys
import time

CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
STALL_MIN = 30
NOWIN = 0x08000000 if os.name == "nt" else 0
DONE_RE = re.compile(r"(?i)done when\s*:\s*(.+)$")
_base = {}


def section(text, name):
    m = re.search(r"(?ims)^## %s[^\n]*\n(.*?)(?=^## |\Z)" % re.escape(name), text)
    return [l.strip()[2:].strip() for l in (m.group(1) if m else "").splitlines() if l.strip().startswith("- ")]


def git(repo, *a, timeout=20):
    try:
        r = subprocess.run(["git", "-C", os.path.expanduser(repo), *a], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, creationflags=NOWIN)
        return r.returncode, r.stdout.strip()
    except Exception as e:
        return 99, str(e)


def base_of(repo):
    if repo not in _base:
        git(repo, "fetch", "-q", "origin", timeout=30)
        _base[repo] = next((b for b in ("origin/master", "origin/main")
                            if git(repo, "rev-parse", "--verify", "-q", b)[0] == 0), None)
    return _base[repo]


def agent_files(agent_id="*"):
    return glob.glob(os.path.join(CLAUDE_DIR, "projects", "*", "*", "subagents", "agent-%s.jsonl" % agent_id))


def tail(path, size):
    with open(path, "rb") as f:
        f.seek(0, 2)
        n = f.tell()
        f.seek(max(0, n - size))
        return f.read().decode("utf-8", "replace").splitlines()


def agent_status(path):
    try:
        lines = tail(path, 300000)
    except OSError:
        return "MISSING"
    done = False
    last = None
    for ln in lines:
        try:
            d = json.loads(ln)
        except Exception:
            continue
        if d.get("type") == "assistant":
            last = d.get("message") or {}
            c = last.get("content")
            if isinstance(c, list) and any(isinstance(x, dict) and x.get("type") == "tool_use" and x.get("name") == "SubagentHandback" for x in c):
                done = True
    if not done and last:
        c = last.get("content")
        has_tool = isinstance(c, list) and any(isinstance(x, dict) and x.get("type") == "tool_use" for x in c)
        done = last.get("stop_reason") == "end_turn" and not has_tool
    if done:
        return "DONE"
    return "STALLED" if time.time() - os.path.getmtime(path) > STALL_MIN * 60 else "RUNNING"


def last_text(path):
    try:
        lines = tail(path, 600000)
    except OSError:
        return ""
    txt = ""
    for ln in lines:
        try:
            d = json.loads(ln)
        except Exception:
            continue
        if d.get("type") != "assistant":
            continue
        c = (d.get("message") or {}).get("content")
        if isinstance(c, str) and c.strip():
            txt = c
        elif isinstance(c, list):
            for x in c:
                if not isinstance(x, dict):
                    continue
                if x.get("type") == "text" and x.get("text", "").strip():
                    txt = x["text"]
                elif x.get("type") == "tool_use" and x.get("name") == "SubagentHandback":
                    m = (x.get("input") or {}).get("message")
                    if m:
                        txt = m
    return txt.strip()


def check(cond):
    try:
        parts = shlex.split(cond, posix=False)
    except ValueError:
        parts = cond.split()
    parts = [p.strip('"') for p in parts]
    if not parts:
        return False, "empty condition"
    kind, args = parts[0].lower(), parts[1:]
    if kind == "file" and len(args) == 1:
        return (lambda ok: (ok, "file exists" if ok else "file not found"))(os.path.exists(os.path.expanduser(args[0])))
    if kind == "agent" and len(args) == 1:
        fs = agent_files(args[0])
        if not fs:
            return False, "agent transcript not found"
        path = max(fs, key=os.path.getmtime)
        st = agent_status(path)
        mt = os.path.getmtime(path)
        idle = int((time.time() - mt) // 60)
        at = time.strftime("%H:%M", time.localtime(mt))
        if st == "DONE":
            res = last_text(path)
            return True, "agent finished\n  last activity %s\n  --- final report ---\n%s\n  --- end ---" % (at, res[:3000] or "(no text result)")
        if st == "RUNNING":
            return "pending", "agent running, last activity %s (%d min ago)" % (at, idle)
        return False, "agent %s: no activity for %d min" % (st, idle)
    if kind == "pushed" and len(args) == 2:
        rc, out = git(args[0], "ls-remote", "--heads", "origin", args[1], timeout=30)
        ok = rc == 0 and bool(out)
        return ok, "branch exists on origin" if ok else "branch not on origin"
    if kind == "on-master" and len(args) == 2:
        b = base_of(args[0])
        if not b:
            return False, "repo has no origin/master or origin/main"
        for ref in (args[1], "origin/" + args[1]):
            if git(args[0], "rev-parse", "--verify", "-q", ref + "^{commit}")[0] == 0:
                return git(args[0], "merge-base", "--is-ancestor", ref, b)[0] == 0, "on " + b
        return False, "ref does not exist"
    if kind == "in-tree" and len(args) == 2:
        b = base_of(args[0])
        if not b:
            return False, "repo has no origin/master or origin/main"
        rc, out = git(args[0], "ls-tree", "-r", "--name-only", b, timeout=30)
        if rc != 0:
            return False, "cannot list tree of " + b
        pat = args[1].replace("\\", "/")
        hit = any(fnmatch.fnmatchcase(f, pat) for f in out.splitlines())
        return hit, ("matches in tree of " + b) if hit else "no match in tree of " + b
    return False, "unrecognized condition (supported: pushed, on-master, in-tree, file, agent)"


def verify(note):
    text = open(note, encoding="utf-8", errors="replace").read()
    red, out = [], []
    agents = [l for l in section(text, "Running agents") if not l.startswith("[")]
    if agents:
        out.append("## Running-agent check")
    for line in agents:
        name = line.split("|", 1)[0].strip()
        m = DONE_RE.search(line)
        aid = re.match(r"(?:agent\s+)?(a[0-9a-f]{16})(?![0-9a-f])", name)
        inferred = not m and aid
        if inferred:
            m = re.match(r"(.+)", "agent " + aid.group(1))
        if not m:
            out.append("❌ %s - no completion condition" % name)
            red.append((name, "no completion condition: check its output, add a condition or re-dispatch"))
            continue
        fails, pend, notes = [], [], []
        for cond in [c.strip() for c in m.group(1).split("&&") if c.strip()]:
            ok, why = check(cond)
            if ok == "pending":
                pend.append("%s (%s)" % (cond, why))
            elif not ok:
                fails.append("%s (%s)" % (cond, why))
            elif "\n" in why:
                notes.append(why)
        if fails:
            out.append("❌ %s - not met: %s" % (name, "; ".join(fails)))
            red.append((name, "not met: " + "; ".join(fails)))
        elif pend:
            out.append("⏳ %s - in progress, do not re-dispatch: %s" % (name, "; ".join(pend)))
        else:
            out.append("✅ %s - %s" % (name, "agent stopped (inferred): read its result" if inferred else "all conditions met"))
            out += notes
    if red:
        out.append("### Added to todo")
        out += ["- [ ] Chase %s: %s" % r for r in red]
    pending = section(text, "Pending dispatch")
    if pending:
        out.append("## Pending dispatch (%d): dispatch now" % len(pending))
        out += ["- [ ] Dispatch " + p for p in pending]
    print("\n".join(out) if out else "nap_verify: no running agents, nothing pending")
    return 1 if (red or pending) else 0


def main():
    files = [x for x in sys.argv[1:] if not x.startswith("--")]
    if not files:
        return 2
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    return verify(files[0])


if __name__ == "__main__":
    sys.exit(main())
