"""No-network verification of truthful sent/queued versus ten-per-day targets."""
from datetime import datetime, timezone
import unittest

from daily_capacity_report import summarize


class CapacityReportTests(unittest.TestCase):
    def test_counts_sent_and_scheduled_separately_on_moscow_day(self):
        today = datetime(2026, 10, 29, 18, 0, tzinfo=timezone.utc)
        catalog = {"episodes": [{"id":"a","auto_preview":True},
                                {"id":"b","auto_preview":True}]}
        queue = [{"id":"s1","dueAt":"2026-10-29T19:25:00Z"}]
        sent = [{"id":"p1","dueAt":"2026-10-29T21:25:00Z",
                 "sentAt":"2026-10-29T17:30:00Z"},
                {"id":"old","dueAt":"2026-10-28T18:15:00Z",
                 "sentAt":"2026-10-28T14:15:00Z"}]
        report = summarize(catalog, {"a"}, {"p1"}, queue, sent, today,
                           model=False, pexels=False)
        self.assertEqual(report["published_today_reported_by_buffer"], 1)
        self.assertEqual(report["scheduled_for_today"], 1)
        self.assertEqual(report["new_unique_scripts_ready_to_render"], 1)
        self.assertIn("BELOW_TEN_SCHEDULED_OR_SENT_TODAY", report["hard_blockers"])
        self.assertIn("PEXELS_API_KEY_NOT_CONFIGURED: CC0 fallback limited",
                      report["hard_blockers"])

    def test_status_is_not_falsely_green_without_credentials(self):
        catalog = {"episodes":[]}
        report = summarize(catalog, set(), set(), [], [],
                           datetime(2026, 10, 29, 18, tzinfo=timezone.utc),
                           model=False, pexels=False)
        self.assertEqual(report["published_today_reported_by_buffer"], 0)
        self.assertGreater(len(report["hard_blockers"]), 0)


if __name__ == "__main__":
    unittest.main()
