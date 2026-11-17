"""Tests for scripts/leak_check.py. All data below is synthetic: python -m unittest discover -s tests -v"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import leak_check as lc  # noqa: E402


def cats(line, allow=None):
    return lc.scan_line(line, allow or {})


class MustReject(unittest.TestCase):
    def test_email(self):
        self.assertIn("email", cats("mail me at someone@acme-corp.net"))

    def test_phone(self):
        self.assertIn("phone", cats("call 0912" + "-345-678"))
        self.assertIn("phone", cats("call +1415" + "5550100"))

    def test_ip_private_and_public(self):
        self.assertIn("ip", cats("host 10.1." + "2.3"))
        self.assertIn("ip", cats("host 8.8." + "4.4"))

    def test_mac(self):
        self.assertIn("mac", cats("nic aa:bb:cc:" + "dd:ee:ff"))

    def test_local_paths(self):
        self.assertIn("local path", cats("C:\\Users\\" + "alice\\docs"))
        self.assertIn("local path", cats("/home/" + "alice/x"))
        self.assertIn("local path", cats("/Users/" + "alice/x"))

    def test_domain_and_share_link(self):
        self.assertIn("domain", cats("see https://intranet.acme-corp.net/wiki"))
        self.assertIn("share link", cats("https://docs.google.com/document/d/abc"))

    def test_ids(self):
        self.assertIn("account id", cats("account 1234567890" + "12"))
        self.assertIn("uuid", cats("id 123e4567-e89b-12d3-" + "a456-426614174000"))
        self.assertIn("session id", cats("session_id: abcdef0123456789" + "abcdef"))

    def test_repo_and_handle(self):
        self.assertIn("repo name", cats("https://github.com/acme-org/secret-repo"))
        self.assertIn("handle", cats("thanks @some-person for this"))

    def test_bypass_marker(self):
        self.assertIn("bypass marker", cats("token = x  # gitleaks" + ":allow"))


class Placeholders(unittest.TestCase):
    def test_accepted(self):
        for line in [
            "api key: <YOUR_API_KEY>",
            "user@example.com",
            "C:\\Users\\<you>\\project",
            "/home/<you>/project",
            "see https://example.com/page",
            "listen on 127.0.0.1",
            "python scripts/leak_check.py <file>",
            "https://github.com/anthropics/claude-code",
        ]:
            self.assertEqual(cats(line), [], line)


class Allowlist(unittest.TestCase):
    def test_allow_domain_and_repo(self):
        self.assertEqual(cats("https://wiki.acme-corp.net/a", {"domain": {"wiki.acme-corp.net"}}), [])
        self.assertEqual(cats("https://github.com/acme-org/x", {"repo": {"acme-org"}}), [])

    def test_file_skip_and_scan(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "note.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write("fine line\nwrite to someone@acme-corp.net\n")
            self.assertEqual(lc.scan_file(p, {}), [(2, "email")])
            self.assertTrue(lc.skipped(p, {"file": {os.path.normpath(p).replace("\\", "/")}}))

    def test_main_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            ok = os.path.join(d, "ok.md")
            bad = os.path.join(d, "bad.md")
            open(ok, "w").write("hello user@example.com\n")
            open(bad, "w").write("ping 10.0.0." + "5\n")
            self.assertEqual(lc.main([ok]), 0)
            self.assertEqual(lc.main([bad]), 1)
            self.assertEqual(lc.main([]), 2)

    def test_matched_text_not_printed(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.md")
            open(bad, "w").write("mail someone@acme-corp.net\n")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                lc.main([bad])
            self.assertNotIn("acme-corp", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
