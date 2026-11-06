"""The direct selector must reject prior legacy and direct receipts."""
import unittest
from unittest.mock import patch
from direct_queue_select import selected_or_none


class DirectSelectorTests(unittest.TestCase):
    @patch("direct_queue_select.select", return_value=None)
    def test_all_legacy_and_direct_receipts_exclude_episodes(self, selector):
        selected_or_none({"episodes": []}, [], [], [
            "publication-receipts/old-a.json",
            "buffer-publication-receipts/old-b.json",
            "render-receipts/old-c.json",
        ], [
            "upload-receipts/by-episode/direct-a.json",
            "upload-receipts/channel/sha.json",
        ])
        excluded = selector.call_args.args[2]
        self.assertEqual(excluded, {"old-a", "old-b", "direct-a"})

if __name__ == "__main__":
    unittest.main()
