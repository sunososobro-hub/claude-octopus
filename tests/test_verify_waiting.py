import importlib.util
import json
import os
import sys
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "nap_verify", os.path.join(os.path.dirname(__file__), "..", "scripts", "nap_verify.py"))
nv = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(nv)


def asst(content, stop="tool_use"):
    return {"type": "assistant", "message": {"content": content, "stop_reason": stop}}


def bg_start():
    return asst([{"type": "tool_use", "name": "Bash", "input": {"command": "gh run watch", "run_in_background": True}}])


def final_text():
    return asst([{"type": "text", "text": "waiting"}], "end_turn")


def notif(status):
    return {"type": "user", "message": {"content": "<task-notification><status>%s</status></task-notification>" % status}}


class AgentStatusTest(unittest.TestCase):
    def status(self, events):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "agent-x.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write("\n".join(json.dumps(e) for e in events) + "\n")
            return nv.agent_status(p)

    def test_waiting_on_own_background_work_is_running(self):
        self.assertEqual(self.status([bg_start(), final_text()]), "RUNNING")

    def test_finished_after_background_completed(self):
        self.assertEqual(self.status([bg_start(), notif("completed"), final_text()]), "DONE")

    def test_plain_end_turn_is_done(self):
        self.assertEqual(self.status([final_text()]), "DONE")

    def test_handback_is_done_even_with_background(self):
        hb = asst([{"type": "tool_use", "name": "SubagentHandback", "input": {"message": "ok"}}])
        self.assertEqual(self.status([bg_start(), hb]), "DONE")


if __name__ == "__main__":
    unittest.main()
