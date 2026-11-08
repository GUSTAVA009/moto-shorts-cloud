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

    def test_real_101_playlist_items_can_hold_100_distinct_video_ids(self):
        """Different playlistItem resources may refer to same provider video."""
        import contextlib
        import io
        from unittest.mock import Mock
        from direct_schedule import youtube_inventory, EXPECTED_CHANNEL
        api=Mock()
        api.channels.return_value.list.return_value.execute.return_value={
            "items":[{"id":EXPECTED_CHANNEL,
                      "contentDetails":{"relatedPlaylists":{"uploads":"UU-channel"}}}]}
        requests=[]
        def get_items(**kwargs):
            page=kwargs.get("pageToken")
            rows=[{"id":"playlist-item-"+str(i),
                   "contentDetails":{"videoId":f"{i%100:011d}"}}
                  for i in range(101)]
            offset={None:0,"p2":50,"p3":100}[page]
            batch=rows[offset:offset+50]
            reply={"items":batch,"pageInfo":{"totalResults":101}}
            next_page={None:"p2","p2":"p3","p3":None}[page]
            if next_page:
                reply["nextPageToken"]=next_page
            return reply
        def get_videos(**kwargs):
            requested=kwargs["id"].split(",")
            requests.extend(requested)
            return {"items":[{"id":id,
                              "status":{"privacyStatus":"private"}} for id in requested]}
        api.playlistItems.return_value.list.side_effect=lambda **kw: (
            Mock(execute=lambda:get_items(**kw)))
        api.videos.return_value.list.side_effect=lambda **kw:(
            Mock(execute=lambda:get_videos(**kw)))
        capture=io.StringIO()
        with contextlib.redirect_stdout(capture):
            self.assertEqual(youtube_inventory(api),[])
        self.assertEqual(len(requests),100)
        self.assertEqual(len(set(requests)),100)
        self.assertIn("playlist_items 101 unique_videos 100",capture.getvalue())
        self.assertIn("duplicate_video_entries 1",capture.getvalue())

    def test_exact_same_playlist_item_overlapping_page_never_counts_as_duplicate_video(self):
        from unittest.mock import Mock
        from direct_schedule import youtube_inventory, EXPECTED_CHANNEL
        api=Mock()
        api.channels.return_value.list.return_value.execute.return_value={
            "items":[{"id":EXPECTED_CHANNEL,
                      "contentDetails":{"relatedPlaylists":{"uploads":"UU-channel"}}}]}
        def items(**kw):
            if not kw.get("pageToken"):
                return {"items":[{"id":"pli-same",
                                  "contentDetails":{"videoId":"12345678901"}}],
                        "pageInfo":{"totalResults":2},
                        "nextPageToken":"next"}
            return {"items":[{"id":"pli-same",
                              "contentDetails":{"videoId":"12345678901"}}],
                    "pageInfo":{"totalResults":2}}
        api.playlistItems.return_value.list.side_effect=lambda **kw:(
            Mock(execute=lambda:items(**kw)))
        api.videos.return_value.list.return_value.execute.return_value={
            "items":[{"id":"12345678901","status":{"privacyStatus":"private"}}]}
        api.search.return_value.list.return_value.execute.return_value={"items":[]}
        with self.assertRaisesRegex(RuntimeError,"CROSSCHECK_INCOMPLETE"):
            youtube_inventory(api)

    def test_independent_owner_api_can_resolve_two_overlapping_uploads_scans(self):
        """Search must independently prove exactly all 101 channel-owned IDs."""
        import contextlib
        import io
        from unittest.mock import Mock
        from direct_schedule import youtube_inventory,EXPECTED_CHANNEL
        api=Mock()
        api.channels.return_value.list.return_value.execute.return_value={
            "items":[{"id":EXPECTED_CHANNEL,
                      "contentDetails":{"relatedPlaylists":{"uploads":"UU-channel"}}}]}
        def playlist(**kwargs):
            page=kwargs.get("pageToken")
            if not page:
                rows=[{"id":"playlist-"+str(i),
                       "contentDetails":{"videoId":f"{i:011d}"}}
                      for i in range(50)]
                return {"items":rows,"pageInfo":{"totalResults":101},
                        "nextPageToken":"overlap"}
            # A corrupt pagination boundary repeats one of the same playlist
            # resources, and is never accepted as a new video.
            return {"items":[{"id":"playlist-49",
                               "contentDetails":{"videoId":f"{49:011d}"}}],
                    "pageInfo":{"totalResults":101}}
        def search(**kwargs):
            token=kwargs.get("pageToken")
            offset={None:0,"p2":50,"p3":100}[token]
            rows=[{"id":{"kind":"youtube#video","videoId":f"{i:011d}"}}
                  for i in range(offset,min(offset+50,101))]
            response={"items":rows}
            nxt={None:"p2","p2":"p3","p3":None}[token]
            if nxt:response["nextPageToken"]=nxt
            return response
        queried=[]
        def videos(**kwargs):
            ids=kwargs["id"].split(",")
            queried.extend(ids)
            return {"items":[{"id":v,"status":{"privacyStatus":"private"}}
                             for v in ids]}
        api.playlistItems.return_value.list.side_effect=lambda **kw:(
            Mock(execute=lambda:playlist(**kw)))
        api.search.return_value.list.side_effect=lambda **kw:(
            Mock(execute=lambda:search(**kw)))
        api.videos.return_value.list.side_effect=lambda **kw:(
            Mock(execute=lambda:videos(**kw)))
        capture=io.StringIO()
        with contextlib.redirect_stdout(capture):
            self.assertEqual(youtube_inventory(api),[])
        self.assertEqual(len(set(queried)),101)
        # Two failed but read-only playlist passes also verified 50 IDs each.
        self.assertEqual(len(queried),201)
        self.assertIn("INDEPENDENT_OWNER_SEARCH_VERIFIED",capture.getvalue())
        self.assertNotIn(f"{40:011d}",capture.getvalue())

    def test_only_valid_live_inventory_may_select_next(self):
        import unittest.mock
        with unittest.mock.patch("direct_schedule.youtube_inventory", return_value=[]):
            stamp = datetime(2026, 11, 9, 0, 0, tzinfo=timezone.utc)
            self.assertEqual(next_verified_slot(object(), now=stamp),
                             "2026-11-09T02:00:00Z")

if __name__ == "__main__":
    unittest.main()
