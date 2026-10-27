"""Safe offline tests for YouTube Shorts public view history."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import views_watch as v

class TestPublicViewMonitor(unittest.TestCase):
    def fixture(self, n=900):
        return {"items":[{"id":v.VIDEO_ID,
            "snippet":{"channelId":v.EXPECTED_CHANNEL,"title":"Наш короткий ролик"},
            "statistics":{"viewCount":str(n),"likeCount":"17","commentCount":"3"}}]}

    def test_read_real_video_stats_shape(self):
        x=v.parse_video(self.fixture())
        self.assertEqual(x["views"],900)
        self.assertEqual(x["likes"],17)
        self.assertEqual(x["comments"],3)

    def test_private_counts_can_be_absent(self):
        x=self.fixture()
        del x["items"][0]["statistics"]["likeCount"]
        self.assertIsNone(v.parse_video(x)["likes"])

    def test_blocks_wrong_channel_or_wrong_video(self):
        x=self.fixture()
        x["items"][0]["snippet"]["channelId"]="UC"+"0"*22
        with self.assertRaises(ValueError):
            v.parse_video(x)
        with self.assertRaises(ValueError):
            v.parse_video({"items":[]})

    def test_rejects_unreliable_views(self):
        x=self.fixture()
        x["items"][0]["statistics"]["viewCount"]="unknown"
        with self.assertRaises(ValueError):
            v.parse_video(x)

    def test_delta_uses_real_elapsed_time(self):
        before={"views":663,"observed_at":"2026-10-27T19:38:00Z"}
        after={"views":987,"observed_at":"2026-10-28T01:38:00Z"}
        delta=v.diff_stats(after,before)
        self.assertEqual(delta["delta_views"],324)
        self.assertEqual(delta["elapsed_hours"],6.0)
        self.assertEqual(delta["views_per_hour"],54.0)

    def test_no_external_key_fails_closed(self):
        with self.assertRaises(RuntimeError):
            v.yt_public_stats("")
        with self.assertRaises(ValueError):
            v.yt_public_stats("x","../bad")

if __name__=="__main__":
    unittest.main()
