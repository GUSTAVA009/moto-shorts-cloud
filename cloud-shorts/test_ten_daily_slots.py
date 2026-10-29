"""Offline verification of 16 real posting slots per day (no publishing)."""
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ten_daily_slots import choose_slot, LOCAL_TIMES, TARGET_PER_DAY


class NinetyMinuteSlotsTests(unittest.TestCase):
    def test_ten_distinct_slots_every_day(self):
        self.assertEqual(len(LOCAL_TIMES), 16)
        self.assertEqual(len(set(LOCAL_TIMES)), 16)
        self.assertEqual(TARGET_PER_DAY, 16)


    def test_exact_ninety_minutes_including_midnight(self):
        from datetime import date, time, timedelta
        tz = ZoneInfo("Europe/Moscow")
        day = date(2026, 10, 30)
        marks = [datetime.combine(day, time(h, m), tz)
                 for h, m in LOCAL_TIMES]
        marks.append(datetime.combine(day + timedelta(days=1),
                                      time(*LOCAL_TIMES[0]), tz))
        for a, b in zip(marks, marks[1:]):
            self.assertEqual((b - a).total_seconds(), 90 * 60)

    def test_early_day_starts_from_first_local_slot(self):
        now = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)
        self.assertEqual(choose_slot([], now), "2026-10-30T03:30:00Z")

    def test_occupied_slots_skipped_without_duplicate(self):
        now = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)
        existing = [{"dueAt": "2026-10-30T03:30:00Z"},
                    {"dueAt": "2026-10-30T05:00:00Z"}]
        self.assertEqual(choose_slot(existing, now), "2026-10-30T06:30:00Z")

    def test_manual_post_near_slot_blocks_collision(self):
        now = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)
        self.assertEqual(
            choose_slot([{"dueAt": "2026-10-30T03:40:00Z"}], now),
            "2026-10-30T05:00:00Z",
        )

    def test_full_day_moves_to_next_day(self):
        now = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)
        tz = ZoneInfo("Europe/Moscow")
        from datetime import date, time
        existing = [datetime.combine(date(2026, 10, 30),
                    time(h, m), tz).astimezone(timezone.utc)
                    for h, m in LOCAL_TIMES]
        self.assertEqual(choose_slot(existing, now), "2026-10-30T21:30:00Z")

    def test_late_evening_picks_next_day(self):
        now = datetime(2026, 10, 30, 20, 0, tzinfo=timezone.utc)
        self.assertEqual(choose_slot([], now), "2026-10-30T21:30:00Z")

    def test_bad_due_at_rejected_not_silently_ignored(self):
        with self.assertRaises(ValueError):
            choose_slot([{"dueAt": "not-an-iso-date"}],
                        datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
