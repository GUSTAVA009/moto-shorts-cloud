"""No-network verification of monthly 330 and daily 12 targets."""
from datetime import datetime, timezone
import unittest

from daily_capacity_report import summarize
from rolling_batches import reconcile


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
        self.assertEqual(report["monthly_minimum_short"],330)
        self.assertEqual(report["daily_target"],12)
        self.assertEqual(report["monthly_delivery_observations"]["baseline_daily_target"],12)
        self.assertEqual(report["scheduled_for_today"], 1)
        self.assertEqual(report["new_unique_scripts_ready_to_render"], 1)
        self.assertIn("BELOW_TWELVE_SCHEDULED_OR_SENT_TODAY", report["hard_blockers"])
        self.assertTrue(report["keyless_editorial_script_reserve"])
        self.assertEqual(report["script_reserve_capacity"], 150000)
        self.assertEqual(report["script_reserve_remaining"], 150000)
        self.assertGreaterEqual(report["unconsumed_curated_pexels_clips"], 0)

    def test_report_shows_verified_rolling_ten_not_scheduled_posts(self):
        batch, _ = reconcile(None, [])
        today = datetime(2026, 10, 30, tzinfo=timezone.utc)
        report = summarize({"episodes":[]}, set(), set(), [{"id":"scheduled"}]*10, [],
                           today, rolling_state=batch)
        self.assertEqual(report["rolling_ten"]["current_pack_progress"], 0)
        self.assertEqual(report["rolling_ten"]["buffer_scheduled_posts"], 10)
        self.assertEqual(report["rolling_ten"]["active_script_drafts_ready"], 10)

    def test_buffer_delivery_errors_are_not_counted_as_sent(self):
        now = datetime(2026, 10, 30, tzinfo=timezone.utc)
        report = summarize({"episodes":[]}, set(), set(), [], [], now,
             errored_posts=[{"id":"post-failed-youtube"}],
             sending_posts=[{"id":"post-not-finished"}])
        self.assertEqual(report["published_today_reported_by_buffer"], 0)
        self.assertEqual(report["buffer_delivery_error_count"], 1)
        self.assertEqual(report["buffer_sending_count"], 1)
        self.assertIn("BUFFER_YOUTUBE_DELIVERY_ERRORS: 1", report["hard_blockers"])

    def test_status_is_not_falsely_green_without_credentials(self):
        catalog = {"episodes":[]}
        report = summarize(catalog, set(), set(), [], [],
                           datetime(2026, 10, 29, 18, tzinfo=timezone.utc),
                           model=False, pexels=False)
        self.assertEqual(report["published_today_reported_by_buffer"], 0)
        self.assertGreater(len(report["hard_blockers"]), 0)
        self.assertTrue(report["keyless_editorial_script_reserve"])


if __name__ == "__main__":
    unittest.main()
