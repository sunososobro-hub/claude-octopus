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
        self.assertTrue(h["updatedInput"]["prompt"].endswith("stop and hand back what is done and the exact next step."))
        self.assertIn("additionalContext", h)

    def test_chinese_wait_ci(self):
        _, out = run({"tool_input": {"prompt": "合併前等 CI 綠"}})
        self.assertIn("additionalContext", out["hookSpecificOutput"])

    def test_bad_input_is_silent(self):
        r = subprocess.run([sys.executable, SCRIPT], input="nope", capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout), (0, ""))



class RepoSettingsTest(unittest.TestCase):
    """The rule must also apply in cloud routine sessions, which use repo-level settings."""

    def test_repo_settings_hook_runs_guard_and_appends_brake(self):
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        with open(os.path.join(root, ".claude", "settings.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        entry = [e for e in cfg["hooks"]["PreToolUse"] if e["matcher"] == "Agent"][0]
        cmd = entry["hooks"][0]["command"]
        self.assertIn("dispatch-guard.py", cmd)
        env = dict(os.environ, CLAUDE_PROJECT_DIR=os.path.abspath(root))
        r = subprocess.run(cmd, shell=True, env=env, capture_output=True, text=True,
                           input=json.dumps({"tool_input": {"prompt": "wait for CI green"}}))
        self.assertEqual(r.returncode, 0)
        p = json.loads(r.stdout)["hookSpecificOutput"]["updatedInput"]["prompt"]
        self.assertIn("60k tokens", p)
        self.assertIn("25 steps", p)


if __name__ == "__main__":
    unittest.main()
