"""Owner 330 finished Shorts/month minimum; production targets do not fake publication."""
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from monthly_capacity import (MINIMUM_MONTHLY_SHORTS,
    BASE_DAILY_SHORTS, MAX_DAILY_CATCHUP_SHORTS, month_capacity)


class MonthContractTests(unittest.TestCase):
    def test_330_in_every_month_including_february(self):
        self.assertEqual(MINIMUM_MONTHLY_SHORTS,400)
        self.assertEqual(BASE_DAILY_SHORTS,14)
        self.assertEqual(MAX_DAILY_CATCHUP_SHORTS,16)
        for year, month, expected in [(2027,2,420),(2028,2,406),
                                      (2026,4,420),(2026,11,420),
                                      (2027,1,434)]:
            result=month_capacity(datetime(year,month,1,12,
                                          tzinfo=timezone.utc))
            self.assertEqual(result["minimum_baseline_monthly"],expected)
            self.assertGreaterEqual(expected,MINIMUM_MONTHLY_SHORTS)
            self.assertEqual(result["daily_catchup_goal"],15 if month == 2 and year == 2027 else 14)

    def test_distinct_sent_receipts_not_scripts_or_scheduled(self):
        now=datetime(2026,11,10,8,tzinfo=timezone.utc)
        state={"p1":"2026-11-01T04:00:00Z",
               "p2":"2026-10-31T18:01:00Z"}
        rows=[{"id":"p1","sentAt":"2026-11-01T04:00:00Z"},
              {"id":"p3","sentAt":"2026-11-10T04:00:00Z"}]
        result=month_capacity(now,state,rows)
        self.assertEqual(result["observed_buffer_sent_this_month"],2)
        self.assertEqual(result["observed_buffer_sent_today"],1)
        self.assertEqual(result["not_yet_verified_against_monthly_minimum"],398)
        self.assertFalse(result["monthly_minimum_confirmed_from_observed_receipts"])
        self.assertFalse(result["claims_complete_youtube_publication"])
        self.assertFalse(result["historical_ledger_completeness_verified"])

    def test_catchup_and_impossible_shortfall_are_honest(self):
        # 19 November, 12 days left: if we only saw 100 sent,
        # 300 more / 12 days > 16 slots/day, so failure must be visible.
        now=datetime(2026,11,19,12,tzinfo=timezone.utc)
        rows={f"p{i}":f"2026-11-{(i%18)+1:02d}T09:00:00Z"
              for i in range(100)}
        result=month_capacity(now,rows)
        self.assertEqual(result["daily_catchup_goal"],16)
        self.assertFalse(result["monthly_goal_achievable_at_current_capacity"])
        self.assertGreater(result["necessary_per_day_without_cap"],16)
        # With 250 already observed, 150 / 12 <= 16 capacity.
        rows={f"p{i}":f"2026-11-{(i%18)+1:02d}T09:00:00Z"
              for i in range(250)}
        result=month_capacity(now,rows)
        self.assertTrue(result["monthly_goal_achievable_at_current_capacity"])
        self.assertEqual(result["daily_catchup_goal"],15 if month == 2 and year == 2027 else 14)

    def test_invalid_conflicting_timestamps_block_fabricated_progress(self):
        now=datetime(2026,11,15,tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError,"CONFLICT"):
            month_capacity(now,{"post-1":"2026-11-03T10:00:00Z"},
                           [{"id":"post-1","sentAt":"2026-11-04T10:00:00Z"}])
        with self.assertRaisesRegex(ValueError,"UNVERIFIED"):
            month_capacity(now,{},[{"id":"queued-no-sent-at"}])
        with self.assertRaisesRegex(ValueError,"TIMEZONE"):
            month_capacity(datetime(2026,11,15))
        with self.assertRaisesRegex(ValueError,"NEEDS_TIMEZONE"):
            month_capacity(now,{"post-1":"2026-11-03T10:00:00"})


if __name__=="__main__":
    unittest.main()
