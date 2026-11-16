"""Tests for the nap/wake scripts (stdlib unittest): python -m unittest discover -s tests -v"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
CFG = tempfile.mkdtemp(prefix="oct-test-")
os.environ["CLAUDE_CONFIG_DIR"] = CFG
os.environ.pop("CLAUDE_PID", None)
sys.path.insert(0, SCRIPTS)
import nap_index as ni  # noqa: E402

spec = importlib.util.spec_from_file_location("auto_wake", os.path.join(SCRIPTS, "auto-wake.py"))
aw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aw)

SID = "11111111-2222-3333-4444-555555555555"
SID2 = "66666666-7777-8888-9999-000000000000"


def cp(h, task, nexts=(), decisions=(), extra=""):
    body = "# %s | 2026-11-16 10:00\n\n## Task\n%s\n\n## Key Findings\n- f\n" % (h, task)
    if decisions:
        body += "\n## Decisions / Watch\n" + "".join("- %s\n" % d for d in decisions)
    if nexts:
        body += "\n## Next Steps\n" + "".join("- %s\n" % n for n in nexts)
    return body + extra


class Base(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(ni.SUM, ignore_errors=True)
        os.makedirs(ni.SUM)

    def put(self, h, text, archive=False):
        d = ni.ARC if archive else ni.SUM
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, h + ".md"), "w", encoding="utf-8") as f:
            f.write(text)

    def index(self, *lines):
        with open(ni.IDX, "w", encoding="utf-8") as f:
            f.write(ni.HEADER + "".join(l + "\n" for l in lines))

    def rows(self):
        return {r["hash"]: r for r in ni.read_index()[0]}

    def cli(self, *args, env=None):
        e = dict(os.environ, CLAUDE_CONFIG_DIR=CFG, PYTHONIOENCODING="utf-8")
        e.update(env or {})
        return subprocess.run([sys.executable, os.path.join(SCRIPTS, "nap_index.py"), *args],
                              capture_output=True, text=True, encoding="utf-8", env=e)


class Hashes(Base):
    def test_new_hash_avoids_live_archive_and_index(self):
        self.put("aaaaaaaa", "x")
        self.put("bbbbbbbb", "x", archive=True)
        self.index("cccccccc | 2026-11-16 10:00 | p | t")
        seq = iter(["aaaaaaaa", "bbbbbbbb", "cccccccc", "dddddddd"])
        with mock.patch.object(ni.secrets, "token_hex", lambda n: next(seq)):
            self.assertEqual(ni.new_hash(), "dddddddd")

    def test_new_hash_cli_is_hex(self):
        out = self.cli("--new-hash").stdout.strip()
        self.assertRegex(out, r"^[0-9a-f]{8}$")

    def test_archive_never_overwrites(self):
        self.put("5e7a2c91", "new one")
        self.put("5e7a2c91", "old one", archive=True)
        self.index("5e7a2c91 | 2026-11-16 10:00 | p | t")
        self.assertEqual(ni.archive_files(["5e7a2c91"]), ["5e7a2c91"])
        with open(os.path.join(ni.ARC, "5e7a2c91.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "old one")
        with open(os.path.join(ni.ARC, "5e7a2c91_2.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "new one")
        self.assertFalse(os.path.exists(os.path.join(ni.SUM, "5e7a2c91.md")))

    def test_archive_identical_copy_is_dropped(self):
        self.put("5e7a2c91", "same")
        self.put("5e7a2c91", "same", archive=True)
        ni.archive_files(["5e7a2c91"])
        self.assertEqual(os.listdir(ni.ARC), ["5e7a2c91.md"])

    def test_non_hex_hash_is_a_valid_hash(self):
        self.put("k7f3a1c2", cp("k7f3a1c2", "kraken"))
        self.index("k7f3a1c2 | 2026-10-13 14:12 | kraken | t")
        self.assertIn("k7f3a1c2", self.rows())
        # auto-wake accepts it too
        self.assertEqual([r[0] for r in aw.rows_now()], ["k7f3a1c2"])

    def test_health_and_repair(self):
        self.put("ae845b5e", cp("ae845b5e", "orphan task"))
        old = time.time() - 7200
        os.utime(os.path.join(ni.SUM, "ae845b5e.md"), (old, old))
        self.put("5e7a2c91", cp("5e7a2c91", "live"))
        self.put("5e7a2c91", cp("5e7a2c91", "old archived"), archive=True)
        self.put("k7f3a1c2", cp("k7f3a1c2", "non hex"))
        self.index("5e7a2c91 | 2026-11-16 10:00 | p | live", "k7f3a1c2 | 2026-10-13 14:12 | kraken | non hex")
        h = "\n".join(ni.health())
        self.assertIn("orphan checkpoint file(s) not in index: ae845b5e", h)
        self.assertIn("hash collision live/archive: 5e7a2c91", h)
        self.assertIn("k7f3a1c2", h)
        r = self.cli("--repair", "--rehash")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(ni.health(), [])
        rows = self.rows()
        self.assertIn("ae845b5e", rows)
        self.assertNotIn("k7f3a1c2", rows)
        self.assertTrue(all(ni.HEX.match(k) for k in rows))
        with open(os.path.join(ni.SUM, "5e7a2c91.md"), encoding="utf-8") as f:
            self.assertIn("live", f.read())
        self.assertEqual(len(os.listdir(ni.ARC)), 1)  # old archived copy kept under a fresh hash
        self.assertTrue([f for f in os.listdir(ni.SUM) if f.startswith("index.md.bak_")])


class CarryForward(Base):
    def setUp(self):
        super().setUp()
        self.put("aaaaaaa1", cp("aaaaaaa1", "acme work", nexts=["[ ] ship the ru voice pack to internal track", "[ ] write release notes for 1.0.0",
                                                               "[x] already done thing about caching"],
                                decisions=["[ ] mobile PRs must base dev branch"]))
        self.index("aaaaaaa1 | 2026-11-16 10:00 | acme | acme work | 4242 | " + SID)

    def check(self, text, **kw):
        self.put("bbbbbbb2", text)
        return ni.check_carry("bbbbbbb2", kw.get("tag", "acme"), kw.get("win", ""), kw.get("sid", SID), ni.read_index()[0])

    def test_lost_items_are_errors(self):
        msgs = self.check(cp("bbbbbbb2", "acme work", nexts=["[ ] ship the ru voice pack to internal track"]))
        text = "\n".join(msgs)
        self.assertIn("ERROR carry-forward: 2 open item(s) from aaaaaaa1", text)
        self.assertIn("write release notes", text)
        self.assertIn("mobile PRs must base dev", text)

    def test_done_or_dropped_marks_satisfy_the_check(self):
        msgs = self.check(cp("bbbbbbb2", "acme work", nexts=["[ ] ship the ru voice pack to internal track",
                                                            "[x] write release notes for 1.0.0"],
                             decisions=["[-] dropped: mobile PRs must base dev branch (superseded)"]))
        self.assertEqual([m for m in msgs if m.startswith("ERROR")], [])

    def test_matches_by_window_even_with_new_session(self):
        msgs = self.check(cp("bbbbbbb2", "acme work", nexts=["[ ] unrelated"]), win="4242", sid=SID2)
        self.assertTrue(any(m.startswith("ERROR") for m in msgs))

    def test_other_scope_is_not_compared(self):
        msgs = self.check(cp("bbbbbbb2", "acme work", nexts=["[ ] unrelated"]), win="9999", sid=SID2, tag="acme:mobile")
        self.assertEqual(msgs, [])

    def test_closed_other_window_same_tag_is_a_merge_source_and_compared(self):
        msgs = self.check(cp("bbbbbbb2", "acme work", nexts=["[ ] unrelated"]), win="9999", sid=SID2)
        self.assertTrue(any(m.startswith("ERROR") for m in msgs))

    def test_upsert_refuses_and_does_not_index(self):
        self.put("bbbbbbb2", cp("bbbbbbb2", "acme work", nexts=["[ ] unrelated"]))
        r = self.cli("bbbbbbb2", "acme work", "acme", "--session", SID)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("ERROR carry-forward", r.stdout)
        self.assertNotIn("bbbbbbb2", self.rows())
        self.assertIn("aaaaaaa1", self.rows())

    def test_upsert_indexes_when_carried_and_archives_same_session(self):
        self.put("bbbbbbb2", cp("bbbbbbb2", "acme work", nexts=["[ ] ship the ru voice pack to internal track",
                                                               "[ ] write release notes for 1.0.0"],
                                decisions=["[ ] mobile PRs must base dev branch"]))
        r = self.cli("bbbbbbb2", "acme work", "acme", "--session", SID)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(list(self.rows()), ["bbbbbbb2"])
        self.assertTrue(os.path.exists(os.path.join(ni.ARC, "aaaaaaa1.md")))

    def test_size_warning(self):
        self.put("bbbbbbb2", cp("bbbbbbb2", "x", extra="\n## Important Context\n" + "y" * 9500))
        self.assertTrue(ni.check_size("bbbbbbb2")[0].startswith("WARN size"))
        self.put("bbbbbbb2", cp("bbbbbbb2", "x"))
        self.assertEqual(ni.check_size("bbbbbbb2"), [])


class Scopes(Base):
    def test_scope_in_tag_and_inheritance(self):
        t = ni.load_tags()
        self.assertEqual(ni.norm_tag("acme", t, scope="Mobile"), "acme:mobile")
        self.assertEqual(ni.norm_tag("acme:main", t), "acme:main")
        self.assertEqual(ni.tag_base("acme:main+x:y"), "acme+x")
        rows = [{"hash": "aaaaaaa1", "date": "2026-11-16 10:00", "tag": "acme:mobile", "task": "", "win": "4242", "sess": SID}]
        self.assertEqual(ni.resolve_tag("acme", "", "4242", SID2, rows, "bbbbbbb2"), "acme:mobile")
        self.assertEqual(ni.resolve_tag("acme", "", "7777", SID2, rows, "bbbbbbb2"), "acme")

    def test_merge_candidates_are_exact_tag_and_skip_live_windows(self):
        for h in ("aaaaaaa1", "aaaaaaa2", "aaaaaaa3", "aaaaaaa4"):
            self.put(h, cp(h, "t"))
        me = str(os.getpid())
        self.index("aaaaaaa1 | 2026-11-16 10:00 | acme:mobile | m | 1 | " + SID,
                   "aaaaaaa2 | 2026-11-16 10:00 | acme:main | main | 1",
                   "aaaaaaa3 | 2026-11-16 10:00 | acme:mobile | live other window | " + me,
                   "aaaaaaa4 | 2026-11-16 10:00 | acme | legacy unscoped")
        rows = ni.read_index()[0]
        got = [r["hash"] for r in ni.merge_candidates("acme:mobile", "555", "zzzzzzzz", rows)]
        self.assertEqual(got, ["aaaaaaa1"])
        self.assertEqual(ni.merge_candidates("misc", "555", "zzzzzzzz", rows), [])
        self.assertEqual([r["hash"] for r in ni.merge_candidates("acme", "555", "zzzzzzzz", rows)], ["aaaaaaa4"])

    def test_archive_refuses_live_window(self):
        self.put("aaaaaaa1", cp("aaaaaaa1", "t"))
        self.put("aaaaaaa2", cp("aaaaaaa2", "t"))
        self.index("aaaaaaa1 | 2026-11-16 10:00 | p | other live window | %d" % os.getpid(),
                   "aaaaaaa2 | 2026-11-16 10:00 | p | closed window | 1")
        r = self.cli("--archive", "aaaaaaa1", "aaaaaaa2", env={"CLAUDE_PID": "123456789"})
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("refused: aaaaaaa1", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(ni.SUM, "aaaaaaa1.md")))
        self.assertTrue(os.path.exists(os.path.join(ni.ARC, "aaaaaaa2.md")))
        self.assertIn("aaaaaaa1", self.rows())
        r = self.cli("--archive", "aaaaaaa1", "--force", env={"CLAUDE_PID": "123456789"})
        self.assertEqual(r.returncode, 0)


class Locking(Base):
    def test_parallel_upserts_keep_every_row(self):
        for i in range(8):
            self.put("cccccc%02d" % i, cp("cccccc%02d" % i, "t%d" % i))
        procs = [subprocess.Popen([sys.executable, os.path.join(SCRIPTS, "nap_index.py"), "cccccc%02d" % i, "task %d" % i, "proj"],
                                  env=dict(os.environ, CLAUDE_CONFIG_DIR=CFG), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                 for i in range(8)]
        self.assertEqual([p.wait() for p in procs], [0] * 8)
        self.assertEqual(len(self.rows()), 8)
        self.assertEqual([f for f in os.listdir(ni.SUM) if ".tmp." in f or f.endswith(".lock")], [])

    def test_stale_lock_is_broken(self):
        with open(ni.LOCK, "w") as f:
            f.write("999999")
        old = time.time() - 600
        os.utime(ni.LOCK, (old, old))
        with ni.locked(timeout=2):
            pass
        self.assertFalse(os.path.exists(ni.LOCK))


class AutoWake(Base):
    def test_whole_text_when_under_cap(self):
        t = cp("aaaaaaa1", "t", nexts=["[ ] a"])
        self.assertEqual(aw.fit(t), (t, []))

    def test_priority_sections_survive_truncation(self):
        t = ("# aaaaaaa1 | 2026-11-16 10:00\n\n## Task\nthe task\n\n## Key Findings\n" + "- finding line\n" * 900 +
             "\n## Decisions / Watch\n- [ ] keep this decision\n\n## Next Steps\n- [ ] keep this step\n\n"
             "## Awaiting Reply\n- waiting on bob\n\n## Important Context\n" + "- ctx\n" * 200)
        text, cut = aw.fit(t)
        self.assertLessEqual(len(text), aw.MAX_CHARS + 200)
        for must in ("the task", "keep this step", "keep this decision", "waiting on bob"):
            self.assertIn(must, text)
        self.assertLess(text.index("## Next Steps"), text.index("## Decisions"))
        self.assertTrue(cut and all(c.startswith(("Key Findings", "Important Context")) for c in cut))

    def test_oversized_decisions_are_marked_partial(self):
        t = ("# aaaaaaa1 | 2026-11-16 10:00\n\n## Task\nx\n\n## Decisions / Watch\n" + "- [ ] a long decision line\n" * 600 +
             "\n## Next Steps\n- [ ] first step\n")
        text, cut = aw.fit(t)
        self.assertIn("first step", text)
        self.assertEqual(cut, ["Decisions / Watch (partial)"])

    def test_cwd_fallback_never_loads_another_windows_checkpoint(self):
        self.put("aaaaaaa1", cp("aaaaaaa1", "mobile work"))
        self.index("aaaaaaa1 | 2026-11-16 10:00 | acme | mobile work | 1 | " + SID)
        got = aw.pick("C:/work/acme", "555", lambda w: False)
        self.assertEqual(got[0], "candidates")
        self.assertEqual(got[1][0][0], "aaaaaaa1")
        self.assertIn("aaaaaaa1", got[2])
        # no window id known at all: still a candidate, not a silent load
        self.assertEqual(aw.pick("C:/work/acme")[0], "candidates")

    def test_main_injects_cut_instruction_with_read_hint(self):
        self.put("aaaaaaa1", cp("aaaaaaa1", "t", nexts=["[ ] a"], extra="\n## Important Context\n" + "z\n" * 6000))
        self.index("aaaaaaa1 | %s | acme | t | 555 | %s" % (time.strftime("%Y-%m-%d %H:%M"), SID))
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "auto-wake.py")], input='{"source":"clear","cwd":"/x"}',
                           capture_output=True, text=True, encoding="utf-8",
                           env=dict(os.environ, CLAUDE_CONFIG_DIR=CFG, CLAUDE_PID="555"))
        out = __import__("json").loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("TOO LONG", out)
        self.assertIn("Read ", out)
        self.assertNotIn("Do not re-read", out)
        self.assertIn("## Next Steps", out)


def tearDownModule():
    shutil.rmtree(CFG, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
