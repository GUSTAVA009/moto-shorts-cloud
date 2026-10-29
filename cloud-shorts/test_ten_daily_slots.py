"""Offline verification of 10 real posting slots per day (no publishing)."""
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ten_daily_slots import choose_slot, LOCAL_TIMES, TARGET_PER_DAY


class TenDailySlotsTests(unittest.TestCase):
    def test_ten_distinct_slots_every_day(self):
        self.assertEqual(len(LOCAL_TIMES), 10)
        self.assertEqual(len(set(LOCAL_TIMES)), 10)
        self.assertEqual(TARGET_PER_DAY, 10)

    def test_early_day_starts_from_first_local_slot(self):
        now = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)
        self.assertEqual(choose_slot([], now), "2026-10-30T05:25:00Z")

    def test_occupied_slots_skipped_without_duplicate(self):
        now = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)
        existing = [{"dueAt": "2026-10-30T05:25:00Z"},
                    {"dueAt": "2026-10-30T07:00:00Z"}]
        self.assertEqual(choose_slot(existing, now), "2026-10-30T08:35:00Z")

    def test_manual_post_near_slot_blocks_collision(self):
        now = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)
        self.assertEqual(
            choose_slot([{"dueAt": "2026-10-30T05:40:00Z"}], now),
            "2026-10-30T07:00:00Z",
        )

    def test_full_day_moves_to_next_day(self):
        now = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)
        tz = ZoneInfo("Europe/Moscow")
        from datetime import date, time
        existing = [datetime.combine(date(2026, 10, 30),
                    time(h, m), tz).astimezone(timezone.utc)
                    for h, m in LOCAL_TIMES]
        self.assertEqual(choose_slot(existing, now), "2026-10-31T05:25:00Z")

    def test_late_evening_picks_next_day(self):
        now = datetime(2026, 10, 30, 20, 0, tzinfo=timezone.utc)
        self.assertEqual(choose_slot([], now), "2026-10-31T05:25:00Z")

    def test_bad_due_at_rejected_not_silently_ignored(self):
        with self.assertRaises(ValueError):
            choose_slot([{"dueAt": "not-an-iso-date"}],
                        datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
