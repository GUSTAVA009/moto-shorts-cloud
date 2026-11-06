"""The autonomous reviewed-MP4 path must wake direct YouTube, not legacy Buffer."""
import unittest
from unittest.mock import Mock
from autonomous_visual_review import dispatch_approved_direct_youtube


class ReviewedOriginalDirectDispatchTests(unittest.TestCase):
    def test_owner_approved_review_dispatches_only_official_youtube(self):
        called=Mock(return_value={})
        dispatch_approved_direct_youtube("moto-forest-e00ff7b3a17b",get=called)
        called.assert_called_once_with(
            "actions/workflows/youtube-direct-queue.yml/dispatches",
            "POST",{"ref":"main"})

    def test_invalid_or_unsafe_episode_slug_is_rejected_before_dispatch(self):
        for slug in ("", "../evil", "MOTOBRATR", "moto/a", "invalid ", None):
            with self.subTest(slug=slug):
                called=Mock()
                with self.assertRaises(ValueError):
                    dispatch_approved_direct_youtube(slug,get=called)
                called.assert_not_called()


if __name__=="__main__":
    unittest.main()
