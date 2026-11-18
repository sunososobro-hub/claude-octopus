import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("agent_brake", os.path.join(HERE, "..", "scripts", "agent-brake.py"))
brake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brake)


def turn(tool_uses=1, prompt_tokens=1000):
    return json.dumps({"message": {"role": "assistant",
                                   "content": [{"type": "tool_use", "name": "Bash"}] * tool_uses,
                                   "usage": {"input_tokens": 10, "cache_read_input_tokens": prompt_tokens}}})


class AgentBrakeTest(unittest.TestCase):
    def run_case(self, lines, payload_extra=None):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "agent.jsonl")
            with open(p, "w") as f:
                f.write("\n".join(lines) + "\n")
            payload = {"agent_id": "a1", "agent_transcript_path": p}
            payload.update(payload_extra or {})
            return brake.build(payload, 25, 60000)

    def test_under_limits_allows(self):
        self.assertIsNone(self.run_case([turn()] * 5))

    def test_step_limit_denies(self):
        res = self.run_case([turn()] * 25)
        self.assertEqual(res["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_context_limit_denies_even_with_few_steps(self):
        res = self.run_case([turn(1, 20000), turn(1, 70000)])
        self.assertIn("70k tokens", res["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertEqual(res["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_handback_tool_is_never_denied(self):
        self.assertIsNone(self.run_case([turn()] * 40, {"tool_name": "SubagentHandback"}))
        self.assertIsNotNone(self.run_case([turn()] * 40, {"tool_name": "Bash"}))

    def test_main_session_is_never_braked(self):
        self.assertIsNone(self.run_case([turn()] * 40, {"agent_id": None}))

    def test_missing_transcript_does_nothing(self):
        self.assertIsNone(brake.build({"agent_id": "a1", "agent_transcript_path": "/nonexistent"}, 1, 1))

    def test_derives_subagent_transcript_from_session_path(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "sess", "subagents"))
            with open(os.path.join(d, "sess", "subagents", "agent-a1.jsonl"), "w") as f:
                f.write("\n".join([turn()] * 30))
            res = brake.build({"agent_id": "a1", "transcript_path": os.path.join(d, "sess.jsonl")}, 25, 60000)
            self.assertIsNotNone(res)


if __name__ == "__main__":
    unittest.main()
