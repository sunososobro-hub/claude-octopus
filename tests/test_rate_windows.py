"""_rate_windows keeps the 7d window when five_hour is null. python -m unittest discover -s tests -v"""
import importlib.util
import os
import unittest
from datetime import datetime, timedelta, timezone

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
spec = importlib.util.spec_from_file_location("usage_analyze", os.path.join(SCRIPTS, "usage-analyze.py"))
ua = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ua)


class RateWindows(unittest.TestCase):
    def test_seven_day_kept_when_five_hour_null(self):
        now = datetime.now(timezone.utc)
        state = {"updated_at": now.isoformat(), "five_hour": None,
                 "seven_day": {"used_percentage": 8, "resets_at": 4102444800}}
        self.assertEqual([w["label"] for w in ua._rate_windows(state, now)], ["7d"])
        self.assertIn("7d ", ua._pulse_compact(state, now))

    def test_reset_days_reasonable_for_real_resets_at(self):
        now = datetime.fromtimestamp(1795500000 - 6.5 * 86400, tz=timezone.utc)
        state = {"updated_at": now.isoformat(), "five_hour": None,
                 "seven_day": {"used_percentage": 8, "resets_at": 1795500000}}
        w = ua._rate_windows(state, now)[0]
        self.assertEqual(w["remain_str"], "6.5d")


if __name__ == "__main__":
    unittest.main()
