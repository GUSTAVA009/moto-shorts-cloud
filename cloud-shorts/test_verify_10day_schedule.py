"""Do not call an empty Buffer queue a ready automated production farm."""
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
import verify_10day_schedule as v


class BufferScheduleAuditTests(unittest.TestCase):
    def run_audit(self, queued, recent):
        output = io.StringIO()
        with patch.object(v, "verify_channel", return_value=(queued, recent)), \
             patch.object(v, "choose_slot", return_value="2026-10-31T00:30:00Z"), \
             redirect_stdout(output):
            v.main()
        return output.getvalue()

    def test_zero_queue_is_not_a_successful_ten_a_day_farm(self):
        result = self.run_audit([], [])
        self.assertIn("BUFFER_SCHEDULE_SETUP_OK_BUT_ZERO_MP4_QUEUED", result)
        self.assertNotIn("GUSTAVA_BUFFER_10_PER_DAY_READY", result)
        line = next(x for x in result.splitlines()
                    if x.startswith("GUSTAVA_BUFFER_SCHEDULING_CONFIGURED"))
        detail = json.loads(line.split(" ", 1)[1])
        self.assertEqual(detail["queued_posts"], 0)
        self.assertEqual(detail["max_actual_posts_per_day"], 16)
        self.assertEqual(detail["normal_daily_target"],14)
        self.assertEqual(detail["monthly_minimum"],400)
        self.assertEqual(detail["available_time_windows"], 16)
        self.assertFalse(detail["content_queue_nonempty"])

    def test_scheduled_content_is_counted_without_claiming_publication(self):
        result = self.run_audit([{"dueAt":"2026-10-31T00:30:00Z"}], [])
        self.assertIn('"content_queue_nonempty": true', result)
        self.assertNotIn("ZERO_MP4_QUEUED", result)
        self.assertIn("READ_ONLY_AUDIT", result)


if __name__ == "__main__":
    unittest.main()
