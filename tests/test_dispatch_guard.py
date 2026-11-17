import json
import os
import subprocess
import sys
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "dispatch-guard.py")


def run(payload):
    r = subprocess.run([sys.executable, SCRIPT], input=json.dumps(payload), capture_output=True, text=True)
    return r.returncode, (json.loads(r.stdout) if r.stdout.strip() else None)


class DispatchGuardTest(unittest.TestCase):
    def test_wait_ci_brief_gets_handback_rules_and_warning(self):
        rc, out = run({"tool_input": {"prompt": "Fix it, then wait CI green and merge", "description": "x"}})
        h = out["hookSpecificOutput"]
        self.assertEqual(rc, 0)
        self.assertIn("hand back at once", h["updatedInput"]["prompt"])
        self.assertEqual(h["updatedInput"]["description"], "x")
        self.assertIn("additionalContext", h)

    def test_plain_brief_gets_rules_without_warning(self):
        _, out = run({"tool_input": {"prompt": "Refactor module"}})
        h = out["hookSpecificOutput"]
        self.assertIn("Stay within 25 steps", h["updatedInput"]["prompt"])
        self.assertNotIn("additionalContext", h)

    def test_rules_not_appended_twice(self):
        _, out = run({"tool_input": {"prompt": "a"}})
        p = out["hookSpecificOutput"]["updatedInput"]["prompt"]
        _, again = run({"tool_input": {"prompt": p}})
        self.assertIsNone(again)

    def test_marker_text_in_brief_does_not_suppress_rules(self):
        _, out = run({"tool_input": {"prompt": "Find refs to [dispatch-guard rules], then wait for CI"}})
        h = out["hookSpecificOutput"]
        self.assertTrue(h["updatedInput"]["prompt"].endswith("read at most 4 images; screenshot "
                                                              "verification belongs to a separate short agent."))
        self.assertIn("additionalContext", h)

    def test_chinese_wait_ci(self):
        _, out = run({"tool_input": {"prompt": "合併前等 CI 綠"}})
        self.assertIn("additionalContext", out["hookSpecificOutput"])

    def test_bad_input_is_silent(self):
        r = subprocess.run([sys.executable, SCRIPT], input="nope", capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
