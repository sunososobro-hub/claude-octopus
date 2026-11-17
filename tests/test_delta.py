"""Regression tests for turns that happen after a checkpoint (stale checkpoint on /clear).

A checkpoint is a snapshot taken when the nap starts. Turns after it used to be lost on auto-wake, so a question the
user had already answered was asked again. python -m unittest discover -s tests -v
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import unittest

from test_nap import CFG, SCRIPTS, SID, SID2, Base, cp, ni

spec = importlib.util.spec_from_file_location("nap_nudge", os.path.join(SCRIPTS, "nap-nudge.py"))
nn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nn)

FAKE_KEY = "AIza" + "SyD3x4mpl3Fak3K3y0123456789abcdefghi"
FAKE_AQ = "AQ." + "Ab8RN6Jfak3fak3fak3fak3fak3fak3fak3"


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + ".000Z"


def jl(kind, t, content, **kw):
    d = {"type": kind, "timestamp": iso(t), "sessionId": SID, "message": {"role": kind, "content": content}}
    d.update(kw)
    return json.dumps(d, ensure_ascii=False)


def human(t, s):
    return jl("user", t, s, origin={"kind": "human"})


def said(t, s, **kw):
    return jl("assistant", t, [{"type": "text", "text": s}], **kw)


def tool(t, name, **inp):
    return jl("assistant", t, [{"type": "tool_use", "name": name, "input": inp}])


class SinceCheckpoint(Base):
    def setUp(self):
        super().setUp()
        self.proj = os.path.join(CFG, "projects", "C--work-acme")
        shutil.rmtree(self.proj, ignore_errors=True)
        os.makedirs(self.proj)
        self.now = int(time.time())
        self.t0 = self.now - 3600  # the nap fork starts here

    def transcript(self, extra=()):
        t0 = self.t0
        lines = [
            human(t0 - 300, "why can it not chat in the group"),
            said(t0 - 200, "The rule is too strict. 修 / 不要？"),
            tool(t0, "Agent", subagent_type="fork", run_in_background=True, description="oct-nap checkpoint",
                 prompt="Run steps 1-6 of oct-nap.md"),
            # the fork is still writing: this turn is already invisible to the checkpoint
            human(t0 + 40, "應該要修吧 就在群組正常聊天阿"),
            tool(t0 + 50, "Agent", description="Fix bot group chat", model="sonnet", prompt="Fix the bot..."),
            said(t0 + 55, "You're right, fixing it now."),
            said(t0 + 70, "✅ /x/summaries/aaaaaaa1.md\nResume: /oct-wake aaaaaaa1"),
            jl("user", t0 + 80, "<task-notification>agent done</task-notification>", origin={"kind": "task-notification"}),
            said(t0 + 300, "修好了，11:10 已經上線 ✅\n\nmore detail"),
            human(t0 + 400, FAKE_KEY + " 給你了 " + FAKE_AQ),
            tool(t0 + 410, "Write", file_path="/x/.secrets/app.env", content="API_KEY=" + FAKE_KEY),
            human(t0 + 500, "合"),
            said(t0 + 510, "sidechain chatter", isSidechain=True),
        ] + list(extra)
        with open(os.path.join(self.proj, SID + ".jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def checkpoint(self, sess=SID, written=None):
        self.put("aaaaaaa1", cp("aaaaaaa1", "secretary bot", nexts=[
            "[ ] Owner answer 修 / 不要 → then dispatch bot group-chat fix + deploy",
            "[ ] Tell owner the trial started"],
            extra="\n## Pending dispatch\n- bot group-chat fix (sonnet). Blocked until owner says 修.\n"))
        t = written or self.t0 + 60  # written by the fork a minute after it started
        os.utime(os.path.join(ni.SUM, "aaaaaaa1.md"), (t, t))
        row = "aaaaaaa1 | %s | acme | secretary bot | 555" % time.strftime("%Y-%m-%d %H:%M", time.localtime(t))
        self.index(row + (" | " + sess if sess else ""))

    def wake(self, payload=None):
        payload = payload or {"source": "clear", "cwd": "/x"}
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "auto-wake.py")], input=json.dumps(payload),
                           capture_output=True, text=True, encoding="utf-8",
                           env=dict(os.environ, CLAUDE_CONFIG_DIR=CFG, CLAUDE_PID="555", PYTHONIOENCODING="utf-8"))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_reply_after_checkpoint_is_shown_as_answered(self):
        self.transcript()
        self.checkpoint()
        out = self.wake()
        self.assertIn("## Since checkpoint", out)
        delta = out.rsplit("## Since checkpoint", 1)[1]
        self.assertIn("應該要修吧", delta)
        self.assertIn("user: 合", delta)
        self.assertIn("[redacted] 給你了 [redacted]", delta)  # pasted keys never reach the wake context
        self.assertNotIn(FAKE_KEY, out)
        self.assertIn("Fix bot group chat", delta)  # the dispatch that already went out
        self.assertIn("已經上線", delta)                         # the deploy report
        # the pending question and the blocked dispatch are flagged as answered, with the owner's words
        ans = [l for l in out.splitlines() if l.startswith("- [x]")]
        self.assertTrue(any("Owner answer 修 / 不要" in l and "應該要修吧" in l for l in ans), out)
        self.assertTrue(any("Blocked until owner says 修" in l for l in ans), out)
        self.assertFalse(any("trial started" in l for l in ans))
        # the model is told the checkpoint is stale; the old "nothing to add" instruction is gone
        self.assertIn("STALE", out)
        self.assertIn("3 user turn", out)
        self.assertNotIn("Do not re-read the file.\n\n# aaaaaaa1", out)
        # nothing from before the nap, no machine turns, no sidechain, not the nap's own output
        self.assertNotIn("why can it not chat", delta)
        self.assertNotIn("task-notification", delta)
        self.assertNotIn("chatter", delta)
        self.assertNotIn("Resume: /oct-wake", delta)

    def test_secrets_are_redacted_and_delta_is_small(self):
        self.transcript(extra=[said(self.t0 + 600 + i, "long reply %d " % i + "x" * 900) for i in range(40)] +
                              [human(self.t0 + 700 + i, "user turn %d " % i + "y" * 500) for i in range(30)])
        self.checkpoint()
        out = self.wake()
        delta = out.rsplit("## Since checkpoint", 1)[1]
        self.assertNotIn(FAKE_KEY, out)
        self.assertNotIn(FAKE_AQ, out)
        self.assertNotIn("SyD3x4mpl3", out)
        self.assertLessEqual(len(delta), 3200)
        self.assertIn("omitted", delta)
        self.assertIn("應該要修吧", out)      # the answer survives the cut (answered line)
        self.assertIn("user turn 29", delta)  # newest turns survive the cut

    def test_fresh_checkpoint_has_no_delta(self):
        self.transcript()
        self.checkpoint(written=self.now + 5)  # no nap marker near the write time, nothing after it
        out = self.wake()
        self.assertNotIn("Since checkpoint", out)
        self.assertNotIn("STALE", out)
        self.assertIn("Do not re-read", out)

    def test_previous_transcript_found_without_session_in_index(self):
        self.transcript()
        self.checkpoint(sess="")
        cur = os.path.join(self.proj, SID2 + ".jsonl")
        with open(cur, "w", encoding="utf-8") as f:
            f.write("{}\n")
        out = self.wake({"source": "clear", "cwd": "/x", "transcript_path": cur, "session_id": SID2})
        self.assertIn("應該要修吧", out)

    def test_cli_prints_delta_for_manual_wake(self):
        self.transcript()
        self.checkpoint()
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "nap_delta.py"), "aaaaaaa1"], capture_output=True,
                           text=True, encoding="utf-8", env=dict(os.environ, CLAUDE_CONFIG_DIR=CFG, PYTHONIOENCODING="utf-8"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("應該要修吧", r.stdout)
        self.assertNotIn(FAKE_KEY, r.stdout)


class ClearReminder(unittest.TestCase):
    def test_reminder_never_says_clear_is_safe_on_a_stale_checkpoint(self):
        st = {"cp": 100.0, "base": 10, "napped": True}
        msg = nn.decide(st, 15, 0, 100.0)
        self.assertTrue(msg)
        self.assertNotIn("/clear anytime", msg)
        self.assertIn("5 turns", msg)
        self.assertIn("/oct-nap", msg)  # re-nap first
        self.assertIsNone(nn.decide(st, 16, 0, 100.0))  # once per nap


if __name__ == "__main__":
    unittest.main()
