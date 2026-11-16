#!/usr/bin/env python3
"""Checkpoint index writer and checker for /oct-nap and /oct-wake (stdlib only, UTF-8 only).

  nap_index.py --new-hash                 print a fresh 8-hex hash (unused in summaries/, archive/ and index.md)
  nap_index.py --merge-candidates HINT [--scope S] [--window W] [--session SID] [--exclude HASH]
      list active checkpoints a nap may merge from: exactly the same project tag (incl. scope),
      never another project, never a checkpoint of another still-open window
  nap_index.py --check HASH [HINT] [--scope S] [--window W] [--session SID]
      lost-to-do check against this window's/session's previous checkpoints + size check; exit 2 = items lost
  nap_index.py HASH "task one-liner" [tag-hint] [--scope S] [--window W] [--session SID] [--date "YYYY-MM-DD HH:MM"]
      run the check above (refuses on lost items; --no-check skips), then upsert the index line
      (replaces an existing HASH line in place), normalize the tag, archive earlier checkpoints of the same session
  nap_index.py --archive HASH [HASH...] [--force]
      move checkpoints to archive/ and drop their lines (refuses a still-open other window unless --force; never overwrites)
  nap_index.py --health                   report orphan files, dangling lines, hash collisions (read-only)
  nap_index.py --repair [--dry-run] [--rehash]
      fix encoding, dangling lines, orphan files, tags, order, live/archive hash collisions;
      --rehash also gives non-hex hashes a fresh hex hash

Line: hash | YYYY-MM-DD HH:MM | tag | task | window id (optional) | session id (optional)
Tag = project or project:scope (scope = short sub-stream such as "mobile"); aliases live in summaries/tags.json.
"""
import contextlib
import difflib
import filecmp
import glob
import json
import os
import re
import secrets
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import oct_core
except Exception:
    oct_core = None

CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
SUM = os.path.join(CLAUDE_DIR, "summaries")
IDX = os.path.join(SUM, "index.md")
ARC = os.path.join(SUM, "archive")
TAGS = os.path.join(SUM, "tags.json")
LOCK = IDX + ".lock"
CAP = getattr(oct_core, "CHECKPOINT_CAP", 9000)  # chars auto-wake injects in full
HEADER = "# Checkpoint Index\n\n| hash | date time | project | task |\n|------|-----------|---------|------|\n"
HASH = re.compile(r"^[0-9a-z]{8}$")  # legacy hashes may be non-hex (e.g. k7f3a1c2)
HEX = re.compile(r"^[0-9a-f]{8}$")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
DATE = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d$")
SCOPE = re.compile(r"^[\w\u4e00-\u9fff-]{1,16}$")
SAME_WINDOW_DAYS = 14  # a window id is a pid and can be reused after a reboot

# Defaults are generic; project names, aliases and cwd hints live in summaries/tags.json (created on first run).
DEFAULT_TAGS = {
    "canonical": ["claude-octopus"],
    "aliases": {},
    "cwd_hints": {"claude-octopus": "claude-octopus"},
    "keywords": {"claude-octopus": ["claude-octopus", "oct-nap", "oct-wake"]},
}


def alive(pid):
    return bool(oct_core and oct_core.pid_alive(pid))


def my_window():
    return oct_core.window_id() if oct_core else ""


def load_tags():
    t = json.loads(json.dumps(DEFAULT_TAGS))
    try:
        with open(TAGS, encoding="utf-8") as f:
            u = json.load(f)
        for k in t:
            if isinstance(u.get(k), type(t[k])):
                if isinstance(t[k], dict):
                    t[k].update(u[k])
                else:
                    t[k] = u[k]
    except (OSError, ValueError):
        pass
    return t


def save_tags(t):
    os.makedirs(SUM, exist_ok=True)
    with open(TAGS, "w", encoding="utf-8", newline="\n") as f:
        json.dump(t, f, ensure_ascii=False, indent=1)
        f.write("\n")


def norm_part(p, t):
    p = p.strip()
    if not p:
        return ""
    low = p.casefold()
    for c in t["canonical"]:
        if c.casefold() == low:
            return c
    if low in t["aliases"]:
        return t["aliases"][low]
    head = re.split(r"[-_ \u3000]", p, maxsplit=1)[0].casefold()  # e.g. "Acme-lag" (separator) or the tag followed directly by other-script text
    for c in t["canonical"]:
        k = c.casefold()
        if k == head or (len(k) >= 2 and low.startswith(k) and not low[len(k)].isascii()):
            return c
    return t["aliases"].get(head, "")


def clean_scope(sc):
    sc = (sc or "").strip().casefold()
    return sc if SCOPE.match(sc) else ""


def tag_base(tag):
    """'acme:mobile+beta' -> 'acme+beta' (project part only)."""
    return "+".join(x.split(":", 1)[0] for x in (tag or "").split("+"))


def norm_tag(hint, t, cwd="", task="", scope=""):
    out = []
    for p in re.split(r"[/+\uff0b,\uff0c]", (hint or "").replace("|", " ")):
        p, _, sc = p.replace("\uff1a", ":").partition(":")
        n = norm_part(p, t)
        if not n and p.strip() and not out and len(p.strip()) <= 24:
            n = p.strip()  # unknown but explicit: new project, keep as typed
        xs = [x for x in n.split("+") if x]
        sc = clean_scope(sc)
        if sc and xs:
            xs[0] = xs[0] + ":" + sc
        for x in xs:
            if x not in out:
                out.append(x)
    if not out and cwd:
        low = cwd.replace("\\", "/").casefold()
        for k, v in t["cwd_hints"].items():
            if k in low and v not in out:
                out.append(v)
                break
    if not out and task:
        pos = []
        for tag, kws in t["keywords"].items():
            hits = [task.casefold().find(k.casefold()) for k in kws if k.casefold() in task.casefold()]
            if hits:
                pos.append((min(hits), tag))
        out = [tag for _, tag in sorted(pos)][:1]
    scope = clean_scope(scope)
    if scope and out and ":" not in out[0]:
        out[0] += ":" + scope
    return "+".join(out[:2]) or "misc"


def decode(b):
    try:
        return b.decode("utf-8"), ""
    except UnicodeDecodeError:
        pass
    try:
        return b.decode("cp950"), "cp950"
    except UnicodeDecodeError:
        return b.decode("utf-8", errors="replace"), "lossy"


def parse(line):
    c = [x.strip() for x in line.split("|")]
    if len(c) < 4 or not HASH.match(c[0]):
        return None
    sess = c.pop() if UUID.match(c[-1]) and len(c) > 4 else ""
    win = ""
    if len(c) > 4 and (c[-1].isdigit() or c[-1] == ""):
        win = c.pop()
    return {"hash": c[0], "date": c[1], "tag": c[2], "task": " / ".join(x for x in c[3:] if x), "win": win, "sess": sess}


def fmt(r):
    s = f"{r['hash']} | {r['date']} | {r['tag']} | {r['task'].replace('|', '/')}"
    if r["win"] or r["sess"]:
        s += f" | {r['win']}"
    if r["sess"]:
        s += f" | {r['sess']}"
    return s


def fix_date(d, h):
    if DATE.match(d):
        return d
    m = re.search(r"(\d{4}-\d\d-\d\d)", d)
    day = m.group(1) if m else time.strftime("%Y-%m-%d")
    tm = re.search(r"\b(\d\d:\d\d)\b", d)
    if tm:
        return f"{day} {tm.group(1)}"
    try:  # no usable time: file mtime if it falls on that day, else midnight
        mt = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(os.path.join(SUM, h + ".md"))))
        if mt.startswith(day):
            return mt
    except OSError:
        pass
    return day + " 00:00"


def read_index():
    """-> (rows, notes). Rows keep file order."""
    notes = []
    try:
        with open(IDX, "rb") as f:
            raw = f.read()
    except OSError:
        return [], notes
    rows = []
    for ln in raw.split(b"\n"):
        s, enc = decode(ln.rstrip(b"\r"))
        if enc:
            notes.append(f"{enc}: {s[:40]}")
        r = parse(s)
        if r:
            rows.append(r)
    return rows, notes


def new_hash():
    """Fresh 8-hex hash, unused as a file stem in summaries/ or archive/ and as an index hash."""
    used = {r["hash"] for r in read_index()[0]}
    for d in (SUM, ARC):
        if os.path.isdir(d):
            used |= {f[:8] for f in os.listdir(d) if f.endswith(".md")}
    while True:
        h = secrets.token_hex(4)
        if h not in used:
            return h


@contextlib.contextmanager
def locked(timeout=20, stale=60):
    """Exclusive lock around an index.md read-modify-write (O_EXCL lock file; a lock older than `stale` s is dead)."""
    os.makedirs(SUM, exist_ok=True)
    end = time.time() + timeout
    while True:
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(LOCK) > stale:
                    os.unlink(LOCK)
                    continue
            except OSError:
                continue
            if time.time() > end:
                sys.exit("index.md is locked by another nap/wake; retry in a few seconds (stale lock: delete %s)" % LOCK)
            time.sleep(0.1)
    try:
        os.write(fd, str(os.getpid()).encode())
        yield
    finally:
        os.close(fd)
        try:
            os.unlink(LOCK)
        except OSError:
            pass


def write_index(rows):
    os.makedirs(SUM, exist_ok=True)
    tmp = "%s.tmp.%d.%s" % (IDX, os.getpid(), secrets.token_hex(3))  # unique per writer
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(HEADER + "".join(fmt(r) + "\n" for r in rows))
        os.replace(tmp, IDX)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def backup():
    if os.path.exists(IDX):
        shutil.copy2(IDX, IDX + ".bak_" + time.strftime("%Y%m%d_%H%M%S"))


def archive_files(hashes):
    """Move live checkpoints into archive/ without ever overwriting an archived file. -> list of moved hashes."""
    os.makedirs(ARC, exist_ok=True)
    moved = []
    for h in hashes:
        src = os.path.join(SUM, h + ".md")
        if not os.path.isfile(src):
            continue
        dst = os.path.join(ARC, h + ".md")
        if os.path.exists(dst):
            if filecmp.cmp(src, dst, shallow=False):
                os.remove(src)  # identical copy already archived
                moved.append(h)
                continue
            n = 2
            while os.path.exists(os.path.join(ARC, "%s_%d.md" % (h, n))):
                n += 1
            dst = os.path.join(ARC, "%s_%d.md" % (h, n))  # same hash, different content: keep both
            print("note: archive/%s.md already exists (different checkpoint); kept both as %s" % (h, os.path.basename(dst)))
        shutil.move(src, dst)
        moved.append(h)
    return moved


def session_cwd(sid):
    for fn in glob.glob(os.path.join(CLAUDE_DIR, "projects", "*", sid + ".jsonl"))[:1]:
        try:
            with open(fn, encoding="utf-8", errors="replace") as f:
                for _, line in zip(range(60), f):
                    m = re.search(r'"cwd":\s*"((?:[^"\\]|\\.)*)"', line)
                    if m:
                        return json.loads('"' + m.group(1) + '"')
        except (OSError, ValueError):
            pass
    return ""


def read_cp(h):
    try:
        with open(os.path.join(SUM, h + ".md"), encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def age_days(date):
    try:
        return (time.time() - time.mktime(time.strptime(date, "%Y-%m-%d %H:%M"))) / 86400
    except ValueError:
        return 0


def resolve_tag(hint, scope, win, sid, rows, h, task="", cwd=""):
    """Tag for a new checkpoint. An omitted scope is inherited from this session's / window's previous
    checkpoint of the same project, so a window keeps its sub-stream across /clear."""
    t = load_tags()
    tag = norm_tag(hint, t, cwd, task, scope)
    if tag != "misc" and ":" not in tag:
        for r in sorted(rows, key=lambda r: r["date"], reverse=True):
            if r["hash"] != h and ((sid and r["sess"] == sid) or (win and r["win"] == win)) and ":" in r["tag"] \
                    and tag_base(r["tag"]) == tag:
                return norm_tag(hint, t, cwd, task, r["tag"].split("+")[0].split(":", 1)[1])
    return tag


# ---------- checkpoint parsing and the lost-to-do check ----------
CBOX = re.compile(r"^\s*[-*+]\s*\[([ xX-])\]\s*(.*\S)")
BULLET = re.compile(r"^\s*[-*+]\s+(.*\S)")


def sections(text):
    """-> [(heading, [lines])] in file order; heading '' = preamble."""
    out, cur = [("", [])], None
    for ln in text.split("\n"):
        if ln.startswith("## "):
            out.append((ln[3:].strip(), []))
        else:
            out[-1][1].append(ln.rstrip("\r"))
    return out


def norm_txt(s):
    return re.sub(r"[\W_]+", "", s.casefold())


def items_of(text):
    """-> (open_items, present): open_items = [(section, text)] for `[ ]` lines in Next Steps / Decisions / Watch;
    present = every checkbox line (any state) plus plain Decisions / Watch bullets, as raw text."""
    open_items, present, plain = [], [], []
    for name, lines in sections(text):
        low = name.casefold()
        if low.startswith("user quotes") or low.startswith("\u539f\u8a71\u7d22\u5f15"):
            continue
        dec = low.startswith("decisions")
        for ln in lines:
            m = CBOX.match(ln)
            if m:
                present.append(m.group(2))
                if m.group(1) == " " and (low.startswith("next steps") or dec):
                    open_items.append((name, m.group(2)))
            elif dec:
                m = BULLET.match(ln)
                if m:
                    present.append(m.group(1))
                    plain.append((name, m.group(1)))
    return open_items, present, plain


def carried(item, present_norm):
    k = norm_txt(item)
    if len(k) < 6:
        return True
    ids = set(re.findall(r"#\d{2,6}", item))
    for n, raw in present_norm:
        if k[:25] == n[:25]:
            return True
        sm = difflib.SequenceMatcher(None, k, n)
        if sm.real_quick_ratio() > 0.6 and sm.quick_ratio() > 0.6 and sm.ratio() > 0.6:
            return True
        if ids and ids <= set(re.findall(r"#\d{2,6}", raw)):
            return True
    return False


def prev_rows(h, tag, win, sid, rows):
    """Checkpoints whose to-dos this one must carry: same session, same-window same-project (recent), and
    merge candidates (same tag, not another open window)."""
    out, seen = [], set()
    merge = merge_candidates(tag, win, h, rows)
    for r in rows:
        if r["hash"] == h or r["hash"] in seen or not os.path.isfile(os.path.join(SUM, r["hash"] + ".md")):
            continue
        same_sess = bool(sid and r["sess"] == sid)
        same_win = bool(win and r["win"] == win and age_days(r["date"]) <= SAME_WINDOW_DAYS
                        and (tag == "misc" or r["tag"] == "misc" or tag_base(r["tag"]).casefold() == tag_base(tag).casefold()))
        if same_sess or same_win or r in merge:
            seen.add(r["hash"])
            out.append(r)
    return out


def check_carry(h, tag, win, sid, rows):
    """-> list of error lines (empty = nothing silently lost)."""
    text = read_cp(h)
    if text is None:
        return ["WARN: no checkpoint file %s.md yet; carry-forward check skipped" % h]
    _, present, _ = items_of(text)
    pn = [(norm_txt(x), x) for x in present]
    errs, warns = [], []
    for r in prev_rows(h, tag, win, sid, rows):
        old = read_cp(r["hash"])
        if old is None:
            continue
        oi, _, plain = items_of(old)
        lost = [(sec, x) for sec, x in oi if not carried(x, pn)]
        if lost:
            errs.append("ERROR carry-forward: %d open item(s) from %s [%s] are missing from %s (not carried as `[ ]`, "
                        "not marked `[x]`, not `[-] dropped: <reason>`):" % (len(lost), r["hash"], r["tag"], h))
            errs += ["  - [ ] %s  (%s)" % (x[:140], sec) for sec, x in lost]
        lp = [x for _, x in plain if not carried(x, pn)]
        if lp:
            warns.append("WARN: %d Decisions / Watch line(s) from %s are missing from %s (carry them or mark `[-] dropped: <reason>`):"
                         % (len(lp), r["hash"], h))
            warns += ["  - %s" % x[:140] for x in lp]
    if errs:
        errs.append("Fix %s.md (carry each as `- [ ]`, `- [x]` or `- [-] dropped: <reason>`) and re-run; nothing was indexed." % h)
    return errs + warns


def check_size(h):
    text = read_cp(h)
    if text is None or len(text) <= CAP:
        return []
    sz = sorted(((len("\n".join(l)) + len(n) + 4, n or "(header)") for n, l in sections(text)), reverse=True)[:4]
    return ["WARN size: %s.md is %d chars (> %d that /clear auto-wake injects in full; the rest needs a Read). Compact it "
            "(shrink Key Findings / Important Context / quotes index first; keep Task, Next Steps, Decisions / Watch). Largest: %s"
            % (h, len(text), CAP, ", ".join("%s %d" % (n, c) for c, n in sz))]


def merge_candidates(tag, win, exclude, rows):
    """Active checkpoints a nap may merge from: exactly this tag (scope included), never `misc`, never a row
    that belongs to another still-open window."""
    if not tag or tag == "misc":
        return []
    return [r for r in rows
            if r["hash"] != exclude and r["tag"].casefold() == tag.casefold()
            and os.path.isfile(os.path.join(SUM, r["hash"] + ".md"))
            and not (r["win"] and r["win"] != win and alive(r["win"]))]


# ---------- commands ----------
def upsert(h, task, hint, scope, win, sid, date, check=True):
    with locked():
        t = load_tags()
        if not os.path.exists(TAGS):
            save_tags(t)
        rows, _ = read_index()
        cwd = session_cwd(sid) if sid else ""
        tag = resolve_tag(hint, scope, win, sid, rows, h, task, cwd)
        if check:
            msgs = check_carry(h, tag, win, sid, rows)
            if any(m.startswith("ERROR") for m in msgs):
                print("\n".join(msgs))
                sys.exit(2)
            if msgs:
                print("\n".join(msgs))
        new = {"hash": h, "date": date or time.strftime("%Y-%m-%d %H:%M"), "tag": tag,
               "task": " ".join(task.split()).replace("|", "/"), "win": win, "sess": sid}
        out, done = [], False
        for r in rows:
            if r["hash"] == h:
                new["sess"] = new["sess"] or r["sess"]
                new["win"] = new["win"] or r["win"]
                out.append(new)
                done = True
            else:
                out.append(r)
        if not done:
            out.insert(0, new)
        gone = []
        if sid:  # successive snapshots of one session: keep the latest
            gone = [r["hash"] for r in out if r["sess"] == sid and r["hash"] != h]
            out = [r for r in out if r["hash"] not in gone]
            archive_files(gone)
        write_index(out)
        print(f"indexed: {h} | {tag}")
        if gone:
            print(f"archived same-session: {' '.join(gone)}")
        if os.path.isfile(os.path.join(ARC, h + ".md")) and os.path.isfile(os.path.join(SUM, h + ".md")):
            print(f"WARN: hash {h} also exists in archive/ (older, different checkpoint); take hashes from --new-hash")
        for m in check_size(h) + [x for x in health(recent_s=600) if x.startswith("orphan")]:
            print(m if m.startswith("WARN") else "WARN " + m)


def cmd_check(h, hint, scope, win, sid):
    rows, _ = read_index()
    tag = resolve_tag(hint, scope, win, sid, rows, h)
    if tag == "misc":  # no hint: fall back to the task line of the file
        tag = resolve_tag(hint, scope, win, sid, rows, h, header_info(h)[2])
    msgs = check_carry(h, tag, win, sid, rows) + check_size(h)
    print("\n".join(msgs) if msgs else "check ok: %s (tag %s)" % (h, tag))
    if any(m.startswith("ERROR") for m in msgs):
        sys.exit(2)


def cmd_archive(hs, force=False):
    me = my_window()
    with locked():
        rows, _ = read_index()
        by = {r["hash"]: r for r in rows}
        ok, refused = [], []
        for h in hs:
            r = by.get(h)
            if r and r["win"] and r["win"] != me and alive(r["win"]) and not force:
                refused.append(h)
                print("refused: %s belongs to window %s which is still open (use --force only if the user says so)" % (h, r["win"]))
            else:
                ok.append(h)
        keep = [r for r in rows if r["hash"] not in ok]
        moved = archive_files(ok)
        write_index(keep)
    print(f"archived {len(moved)}, dropped {len(rows) - len(keep)} index line(s)")
    if refused:
        sys.exit(1)


def header_info(h):
    """(date, tag hint, task) from a checkpoint file."""
    try:
        with open(os.path.join(SUM, h + ".md"), encoding="utf-8", errors="replace") as f:
            txt = f.read(6000)
    except OSError:
        return "", "", ""
    first = txt.split("\n", 1)[0]
    date = (re.search(r"(\d{4}-\d\d-\d\d(?: \d\d:\d\d)?)", first) or [None, ""])[1]
    hint = ""
    m = re.match(r"#\s*\w{8}\s*\|[^|]*\|\s*([^|]+?)\s*(?:\||$)", first)
    if m:
        hint = m.group(1)
    m = re.search(r"[\uff08(][^)\uff09]*,\s*([^,)\uff09]+)[)\uff09]\s*$", first)
    if m:
        hint = hint or m.group(1)
    m = re.search(r"^##\s*(?:Task|\u4efb\u52d9)\s*\n+(.+)", txt, re.M)
    task = ""
    if m:
        task = m.group(1).strip()
        task = re.split(r"(?<=[\u3002.\uff1b;])\s", task, maxsplit=1)[0][:110].rstrip("\u3002 ")
    return date, hint, task


def listing(d):
    return {f[:-3] for f in os.listdir(d) if f.endswith(".md") and HASH.match(f[:-3])} if os.path.isdir(d) else set()


def health(recent_s=0):
    """Read-only index/file consistency report -> list of lines."""
    rows, notes = read_index()
    files, arch = listing(SUM), listing(ARC)
    out = []
    if notes:
        out.append("encoding: %d garbled index line(s)" % len(notes))
    hs = [r["hash"] for r in rows]
    dup = sorted({h for h in hs if hs.count(h) > 1})
    if dup:
        out.append("duplicate index lines: " + " ".join(dup))
    dang = sorted(h for h in set(hs) if h not in files) if files else []
    if dang:
        out.append("dangling index lines (no file): " + " ".join(dang))
    orph = []
    for h in sorted(files - set(hs)):
        if recent_s and time.time() - os.path.getmtime(os.path.join(SUM, h + ".md")) < recent_s:
            continue  # another window may be between writing the file and indexing it
        _, _, task = header_info(h)
        try:
            with open(os.path.join(SUM, h + ".md"), encoding="utf-8", errors="replace") as f:
                first = f.readline()
        except OSError:
            continue
        if task and first.startswith("#") and h in first:
            orph.append(h)
    if orph:
        out.append("orphan checkpoint file(s) not in index: %s (run nap_index.py --repair)" % " ".join(orph))
    col = sorted(files & arch)
    if col:
        out.append("hash collision live/archive: %s (run nap_index.py --repair)" % " ".join(col))
    bad = sorted(h for h in set(hs) | files if not HEX.match(h))
    if bad:
        out.append("note: non-hex hash(es) accepted: " + " ".join(bad) + " (--repair --rehash renames them)")
    return out


def rename_cp(src, h_old, h_new):
    """Rename a checkpoint file and fix its '# hash | date' header line."""
    with open(src, "rb") as f:
        raw = f.read()
    nl = raw.find(b"\n")
    first, rest = (raw, b"") if nl < 0 else (raw[:nl], raw[nl:])
    first = first.replace(h_old.encode(), h_new.encode(), 1)
    dst = os.path.join(os.path.dirname(src), h_new + ".md")
    with open(dst, "wb") as f:
        f.write(first + rest)
    os.remove(src)


def repair(dry=False, sessions=None, tag_fix=None, rehash=False):
    t = load_tags()
    rows, notes = read_index()
    files, arch = listing(SUM), listing(ARC)
    log = [f"encoding repaired/lossy lines: {len(notes)}"] if notes else []
    # dedupe (newest date wins), drop dangling
    best = {}
    for r in rows:
        r["date"] = fix_date(r["date"], r["hash"])
        if r["hash"] not in best or r["date"] >= best[r["hash"]]["date"]:
            best[r["hash"]] = r
    if len(best) < len(rows):
        log.append(f"duplicate hash lines merged: {len(rows) - len(best)}")
    dangling = [h for h in best if h not in files] if files else []
    for h in dangling:
        del best[h]
    if dangling:
        log.append("dangling dropped (" + ("archived" if all(h in arch for h in dangling) else "no file") + "): " + " ".join(dangling))
    # orphans
    orphans = []
    for h in sorted(files - set(best)):
        date, hint, task = header_info(h)
        if not task:
            continue
        try:
            with open(os.path.join(SUM, h + ".md"), encoding="utf-8", errors="replace") as f:
                if h not in f.readline():
                    continue
        except OSError:
            continue
        best[h] = {"hash": h, "date": fix_date(date, h), "tag": hint, "task": task, "win": "", "sess": ""}
        orphans.append(h)
    if orphans:
        log.append("orphan files indexed: " + " ".join(orphans))
    for h, r in best.items():
        if sessions and not r["sess"] and h in sessions:
            r["sess"] = sessions[h]
        r["tag"] = norm_tag(r["tag"], t, task=r["task"])
        if tag_fix:
            r["tag"] = tag_fix(r)
    # same-session supersession (needs session column)
    by = {}
    for r in best.values():
        if r["sess"]:
            by.setdefault(r["sess"], []).append(r)
    gone = []
    for rs in by.values():
        rs.sort(key=lambda r: r["date"])
        gone += [r["hash"] for r in rs[:-1]]
    for h in gone:
        best.pop(h, None)
    if gone:
        log.append("same-session archived: " + " ".join(gone))
    # hash identity: an archived file that shares its hash with a live checkpoint gets a fresh hash;
    # --rehash also replaces non-hex live hashes
    renames = []
    for h in sorted(files & arch):
        renames.append((os.path.join(ARC, h + ".md"), h, None))
    if rehash:
        renames += [(os.path.join(SUM, h + ".md"), h, None) for h in sorted(files) if not HEX.match(h) and h in best]
    out_best = best
    if renames:
        log.append("rehash: " + " ".join("%s%s" % (h, "(archive)" if os.sep + "archive" + os.sep in src else "") for src, h, _ in renames))
    if not dry:
        backup()
        for src, h, _ in renames:
            n = new_hash()
            rename_cp(src, h, n)
            if os.path.dirname(src) == SUM and h in out_best:
                r = out_best.pop(h)
                r["hash"] = n
                out_best[n] = r
            log.append("  %s -> %s" % (h, n))
    out = sorted(out_best.values(), key=lambda r: r["date"], reverse=True)
    log.append(f"index lines: {len(rows)} -> {len(out)}")
    if not dry:
        archive_files(gone)
        write_index(out)
        if not os.path.exists(TAGS):
            save_tags(t)
    print("\n".join(log))


def main():
    a = sys.argv[1:]
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    def opt(name, default=""):
        if name in a:
            i = a.index(name)
            v = a[i + 1] if i + 1 < len(a) else ""
            del a[i:i + 2]
            return v
        return default

    def flag(name):
        if name in a:
            a.remove(name)
            return True
        return False

    if "--new-hash" in a:
        print(new_hash())
        return
    if "--health" in a:
        msgs = health()
        print("\n".join(msgs) if msgs else "health ok")
        return
    if "--repair" in a:
        sf = opt("--sessions")
        sess = None
        if sf:
            with open(sf, encoding="utf-8") as f:
                sess = {k: v["session"] for k, v in json.load(f).items() if v.get("session")}
        dry, rh = flag("--dry-run"), flag("--rehash")
        if dry:
            repair(True, sess, rehash=rh)
        else:
            with locked():
                repair(False, sess, rehash=rh)
        return
    force, nocheck = flag("--force"), flag("--no-check")
    win, sid, date, scope, excl = opt("--window"), opt("--session"), opt("--date"), opt("--scope"), opt("--exclude")
    if "--archive" in a:
        cmd_archive([x for x in a if HASH.match(x)], force)
        return
    win = win if win.isdigit() else my_window()
    sid = sid or os.environ.get("CLAUDE_SESSION_ID", "")
    if sid.startswith("$") or not UUID.match(sid):
        sid = ""
    if "--merge-candidates" in a:
        a.remove("--merge-candidates")
        rows, _ = read_index()
        tag = resolve_tag(a[0] if a else "", scope, win, sid, rows, excl)
        c = merge_candidates(tag, win, excl, rows)
        print("tag: %s" % tag)
        for r in c:
            print("%s | %s | %s | %s" % (r["hash"], r["date"], r["tag"], r["task"]))
        if not c:
            print("(none)")
        return
    if "--check" in a:
        a.remove("--check")
        if not a or not HASH.match(a[0]):
            sys.exit(__doc__)
        cmd_check(a[0], a[1] if len(a) > 1 else "", scope, win, sid)
        return
    if len(a) < 2 or not HASH.match(a[0]):
        sys.exit(__doc__)
    upsert(a[0], a[1], a[2] if len(a) > 2 else "", scope, win, sid, date, not nocheck)


if __name__ == "__main__":
    main()
