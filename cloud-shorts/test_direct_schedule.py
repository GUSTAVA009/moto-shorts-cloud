"""Offline tests of real-provider inventory and 15-per-day schedule. Never upload."""
import unittest
from datetime import datetime, timezone
from direct_schedule import release_times_from_items, next_verified_slot
from ten_daily_slots import BASE_POSTS_PER_DAY, LOCAL_TIMES


class DirectScheduleTests(unittest.TestCase):
    def test_fifteen_regular_slots_and_sixteen_total(self):
        self.assertEqual(BASE_POSTS_PER_DAY, 15)
        self.assertEqual(len(LOCAL_TIMES), 16)

    def test_private_draft_does_not_count_as_scheduled(self):
        self.assertEqual(release_times_from_items([
            {"id": "abcdefghijk", "status": {"privacyStatus": "private"}},
            {"id": "bcdefghijkl", "status": {"privacyStatus": "private",
                                         "publishAt": "2026-11-09T03:30:00Z"}},
            {"id": "cdefghijklm", "status": {"privacyStatus": "public"},
             "snippet": {"publishedAt": "2026-11-09T05:00:00Z"}}
        ]), [{"dueAt": "2026-11-09T03:30:00Z"},
             {"dueAt": "2026-11-09T05:00:00Z"}])

    def test_bad_provider_state_is_blocked(self):
        with self.assertRaisesRegex(RuntimeError, "INCONSISTENT"):
            release_times_from_items([{"id": "abcdefghijk", "status": {
                "privacyStatus": "public", "publishAt": "2026-11-09T03:30:00Z"}}])
        with self.assertRaisesRegex(RuntimeError, "DUPLICATE"):
            release_times_from_items([{"id": "abcdefghijk"}, {"id": "abcdefghijk"}])

    def test_live_upload_api_anomaly_logs_counts_without_private_ids(self):
        import contextlib
        import io
        from unittest.mock import Mock
        from direct_schedule import youtube_inventory,EXPECTED_CHANNEL
        api=Mock()
        api.channels.return_value.list.return_value.execute.return_value={
            "items":[{"id":EXPECTED_CHANNEL,
                      "contentDetails":{"relatedPlaylists":{"uploads":"UU-channel"}}}]}
        api.playlistItems.return_value.list.return_value.execute.return_value={
            "items":[{"contentDetails":{"videoId":"SECRET-VIDEO-ID-PLACEHOLDER"}}],
            "pageInfo":{"totalResults":9}}
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError,"PLAYLIST_INCOMPLETE_OR_DUPLICATE"):
                youtube_inventory(api)
        self.assertIn("YOUTUBE_UPLOAD_PLAYLIST_SAFE_DIAG",output.getvalue())
        self.assertIn("invalid_id_count 1",output.getvalue())
        self.assertNotIn("SECRET-VIDEO-ID-PLACEHOLDER",output.getvalue())

    def test_only_valid_live_inventory_may_select_next(self):
        import unittest.mock
        with unittest.mock.patch("direct_schedule.youtube_inventory", return_value=[]):
            stamp = datetime(2026, 11, 9, 0, 0, tzinfo=timezone.utc)
            self.assertEqual(next_verified_slot(object(), now=stamp),
                             "2026-11-09T02:00:00Z")

if __name__ == "__main__":
    unittest.main()
