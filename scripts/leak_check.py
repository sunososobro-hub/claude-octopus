#!/usr/bin/env python3
"""Pre-submission check for identifiers that should not be published (stdlib only).

Usage: python scripts/leak_check.py [--allow FILE] [--text FILE | PATH ...]
--text FILE scans one text file (an issue or PR body draft) before posting it.
Exit 0 = clean, 1 = something matched, 2 = usage error.

Any match rejects the whole file: nothing is redacted, and the matched text is never
printed (only category, file and line number). When unsure, a line counts as a match.
Placeholders are fine: <YOUR_API_KEY>, user@example.com, C:\\Users\\<you>, example.com,
127.0.0.1.

Allowlist (optional, owner-edited): one entry per line, "kind:value  # reason", where
kind is email, domain, ip, handle, repo (GitHub owner), repopath (owner/repo) or file (path prefix to skip).
The owner of this repository (from GITHUB_REPOSITORY or the origin remote) is always allowed.
"""
import os
import re
import subprocess
import sys

PLACEHOLDER_DOMAINS = {"example.com", "example.org", "example.net", "localhost", "invalid", "test"}
PLACEHOLDER_IPS = {"127.0.0.1", "0.0.0.0", "255.255.255.255"}
PLACEHOLDER_NAMES = {"you", "user", "username", "name", "your_name", "yourname", "me", "foo", "bar", "example", "x"}
ALWAYS_OK_DOMAINS = {
    "anthropic.com", "github.com", "githubusercontent.com", "github.io", "claude.ai", "claude.com",
    "python.org", "pypi.org", "pythonhosted.org", "npmjs.com", "npmjs.org", "nodejs.org", "gitleaks.io",
    "readthedocs.io", "w3.org", "json-schema.org", "shields.io", "wikipedia.org", "mozilla.org",
    "microsoft.com", "stackoverflow.com",
}
# decorators and doc-comment tags that look like @handles
NOT_HANDLES = {
    "staticmethod", "classmethod", "property", "dataclass", "abstractmethod", "override", "wraps", "cache",
    "param", "params", "returns", "return", "type", "typedef", "throws", "example", "see", "deprecated",
    "since", "author", "todo", "link", "default", "private", "public", "internal", "callback", "template",
}
MODEL_PREFIXES = ("claude", "gpt", "gemini", "llama", "mistral", "opus", "sonnet", "haiku", "text-embedding")
BARE_TLDS = "com|net|org|io|dev|ai|edu|gov|info|biz|xyz|cloud|site|tw|cn|jp|uk|de|fr|kr|ru|in|br"
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".pyc", ".woff", ".woff2"}
MAX_BYTES = 2_000_000
FILE_TLDS = {"py", "md", "json", "js", "sh", "txt", "yml", "yaml", "toml", "html", "css", "ts", "cfg", "ini", "log", "lock"}

RX = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)"),
    # E.164 (+ and 8-15 digits, optional separators), (415) 555-0100, 415-555-0100, 0912-345-678
    "phone": re.compile(
        r"(?<![\w.+-])(?:\+[1-9](?:[\s.-]?\d){7,14}|\(\d{2,4}\)[\s-]?\d{3,4}[\s-]\d{3,4}"
        r"|\d{2,4}-\d{3,4}-\d{3,4})(?![\w-]|\.\w)"),
    "ip": re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])"),
    "mac": re.compile(r"(?<![0-9A-Fa-f:-])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:-])"),
    "local path": re.compile(
        r"(?:(?<![\w])[A-Za-z]:[\\/]+(?i:Users)[\\/]+|(?<![\w.-])/home/|(?<![\w.-])/Users/)([^\\/\s\"'`<>]+)"),
    # Claude project directory encoding of a local path: C--Users-alice-proj, -Users-alice-proj, -home-alice-proj
    "encoded path": re.compile(r"(?:(?<![\w])[A-Za-z]--Users-|(?<![\w-])-(?:Users|home)-)([A-Za-z0-9_.]+)"),
    "bare domain": re.compile(r"(?<![\w@.:/-])((?:[A-Za-z0-9-]+\.)+(?:%s))(?![\w-]|\.\w)" % BARE_TLDS, re.I),
    "repo shorthand": re.compile(
        r"(?:gh\s+(?:repo\s+(?:clone|view|fork)|pr|issue|run)|git\s+clone|--repo[ =]|\s-R\s|repos/|"
        r"GITHUB_REPOSITORY[=:]\s*|\brepo(?:sitory)?\s*[:=]\s*)\s*[\"']?([A-Za-z0-9][A-Za-z0-9-]*)/([A-Za-z0-9_.-]+)"),
    "domain": re.compile(r"https?://([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)", re.I),
    "share link": re.compile(
        r"https?://(?:[\w-]+\.)*(?:docs\.google\.com|drive\.google\.com|dropbox\.com|notion\.so|notion\.site|"
        r"claude\.ai/(?:artifact|share|chat|code)|chatgpt\.com/share|1drv\.ms|onedrive\.live\.com)[^\s\"'<>)]*", re.I),
    "account id": re.compile(
        r"(?<![\w.-])(?:G-[A-Z0-9]{8,}|UA-\d{4,}-\d+|[a-z][a-z0-9-]{4,28}-[a-z0-9]{4,}-\d{3,}|properties/\d{6,})(?![\w-])"),
    "session id": re.compile(r"session[_ -]?(?:id)?[\"']?\s*[:=/]\s*[\"']?[A-Za-z0-9_-]{16,}", re.I),
    "uuid": re.compile(r"(?<![0-9A-Fa-f-])[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}(?![0-9A-Fa-f-])"),
    "repo name": re.compile(r"github\.com[/:]([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", re.I),
    "handle": re.compile(r"(?<![\w@./+-])@([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))(?![\w@.-]*\.[A-Za-z])"),
    "bypass marker": re.compile(r"\bgitleaks:allow|\bnosec\b|\bleak[-_ ]?check:\s*(?:ignore|skip|allow)", re.I),
}


def load_allow(path):
    out = {}
    if not path:
        return out
    with open(path, encoding="utf-8") as f:
        for raw in f:
            s = raw.split("#", 1)[0].strip()
            if ":" in s:
                k, v = s.split(":", 1)
                out.setdefault(k.strip().lower(), set()).add(v.strip().lower())
    return out


def own_owner():
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        return repo.split("/")[0].lower()
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    m = RX["repo name"].search(url)
    return m.group(1).lower() if m else ""


def skipped(path, allow):
    norm = os.path.normpath(path).replace("\\", "/")
    return any(norm == f or norm.startswith(f.rstrip("/") + "/") for f in allow.get("file", ()))


def domain_ok(d, allow):
    d = d.lower().rstrip(".")
    if d in allow.get("domain", ()):
        return True
    return any(d == ok or d.endswith("." + ok) for ok in PLACEHOLDER_DOMAINS | ALWAYS_OK_DOMAINS)


def email_ok(addr, domain, allow):
    """Placeholder, noreply and allowlisted addresses only; a real mailbox on a public domain is a match."""
    addr, domain = addr.lower(), domain.lower().rstrip(".")
    local = addr.rsplit("@", 1)[0]
    if addr in allow.get("email", ()) or domain in allow.get("domain", ()):
        return True
    if any(domain == d or domain.endswith("." + d) for d in PLACEHOLDER_DOMAINS):
        return True
    return domain.endswith("noreply.github.com") or local == "noreply" or local.startswith("noreply+")


def ip_ok(ip, allow):
    parts = ip.split(".")
    if any(int(p) > 255 for p in parts):
        return True  # not an address (version string, etc.)
    if ip in PLACEHOLDER_IPS or ip in allow.get("ip", ()):
        return True
    # documentation ranges (RFC 5737) are placeholders; private ranges are NOT
    return ip.startswith(("192.0.2.", "198.51.100.", "203.0.113."))


def scan_line(line, allow):
    """Return the sorted category names matched on this line (never the matched text)."""
    hits = set()
    for m in RX["email"].finditer(line):
        if email_ok(m.group(0), m.group(1), allow):
            continue
        if m.group(1).split(".")[-1].lower() in FILE_TLDS:
            continue
        hits.add("email")
    if RX["phone"].search(line):
        hits.add("phone")
    for m in RX["ip"].finditer(line):
        if not ip_ok(m.group(0), allow):
            hits.add("ip")
    if RX["mac"].search(line):
        hits.add("mac")
    for m in RX["local path"].finditer(line):
        name = m.group(1)
        if name.lower() in PLACEHOLDER_NAMES or name.startswith(("<", "%", "$", "{", "~")):
            continue
        hits.add("local path")
    for m in RX["encoded path"].finditer(line):
        if m.group(1).lower() not in PLACEHOLDER_NAMES:
            hits.add("local path")
    for m in RX["domain"].finditer(line):
        if not domain_ok(m.group(1), allow):
            hits.add("domain")
    for m in RX["bare domain"].finditer(line):
        if not domain_ok(m.group(1), allow):
            hits.add("domain")
    if RX["share link"].search(line):
        hits.add("share link")
    for m in RX["account id"].finditer(line):
        if not m.group(0).lower().startswith(MODEL_PREFIXES):
            hits.add("account id")
    if RX["session id"].search(line):
        hits.add("session id")
    if RX["uuid"].search(line):
        hits.add("uuid")
    for m in RX["repo name"].finditer(line):
        owner = m.group(1).lower()
        if owner in allow.get("repo", ()) or owner in PLACEHOLDER_NAMES | {"owner", "org", "anthropics", "users", "orgs", "repos"} or owner.startswith("<"):
            continue
        if m.group(1).lower() + "/" + m.group(2).lower() in allow.get("repopath", ()):
            continue
        hits.add("repo name")
    for m in RX["repo shorthand"].finditer(line):
        owner = m.group(1).lower()
        if owner in allow.get("repo", ()) or owner in PLACEHOLDER_NAMES | {"owner", "org", "anthropics", "https", "http"}:
            continue
        if owner + "/" + m.group(2).lower().rstrip(".") in allow.get("repopath", ()):
            continue
        hits.add("repo name")
    for m in RX["handle"].finditer(line):
        h = m.group(1).lower()
        if h in NOT_HANDLES or h in PLACEHOLDER_NAMES or h in allow.get("handle", ()) or h.startswith(("types", "anthropic")):
            continue
        hits.add("handle")
    if RX["bypass marker"].search(line):
        hits.add("bypass marker")
    return sorted(hits)


def scan_file(path, allow):
    if os.path.splitext(path)[1].lower() in SKIP_EXT:
        return []
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return [(0, "file too large")]
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return [(0, "unreadable")]
    if b"\0" in data:
        return [(0, "binary content")]
    out = []
    for i, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
        for cat in scan_line(line, allow):
            out.append((i, cat))
    return out


def iter_paths(args):
    for a in args:
        if os.path.isdir(a):
            for root, dirs, files in os.walk(a):
                dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "node_modules"}]
                for n in files:
                    yield os.path.join(root, n)
        else:
            yield a


def main(argv):
    args = list(argv)
    allow_path = None
    if args[:1] == ["--allow"] and len(args) >= 2:
        allow_path, args = args[1], args[2:]
    if args[:1] == ["--text"]:
        if len(args) != 2:
            print("usage: leak_check.py --text FILE", file=sys.stderr)
            return 2
        args = args[1:]
    if not args:
        print("usage: leak_check.py [--allow FILE] PATH [PATH ...]", file=sys.stderr)
        return 2
    if args[:1] == ["--"]:
        args = args[1:]
    if not args:
        print("usage: leak_check.py [--allow FILE] PATH [PATH ...]", file=sys.stderr)
        return 2
    allow = load_allow(allow_path)
    owner = own_owner()
    if owner:
        allow.setdefault("repo", set()).add(owner)
    bad = 0
    for p in iter_paths(args):
        if skipped(p, allow):
            continue
        for line, cat in scan_file(p, allow):
            print("REJECT %s:%d: %s" % (p, line, cat))
            bad += 1
    if bad:
        print("%d match(es). Remove the item(s) and retry; placeholders such as <YOUR_API_KEY>, "
              "user@example.com or C:\\Users\\<you> are fine." % bad)
        return 1
    print("leak_check: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
