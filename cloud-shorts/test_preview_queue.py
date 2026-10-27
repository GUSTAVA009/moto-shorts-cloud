"""Cloud preview queue pure/offline behavior tests."""
import unittest
import preview_queue as pq


class TestPreviewQueue(unittest.TestCase):
    def test_only_explicitly_approved_unused_episodes(self):
        episodes = [
            {"id": "first", "auto_preview": False},
            {"id": "second", "auto_preview": True},
            {"id": "third", "auto_preview": True},
        ]
        self.assertEqual(pq.pick(episodes, lambda i: i == "third"), "second")
        self.assertEqual(pq.pick(episodes, lambda i: i in {"second", "third"}), None)
        self.assertEqual(pq.pick(episodes, lambda i: False), "second")

    def test_exhausted_queue_returns_none(self):
        self.assertIsNone(pq.pick([], lambda _: False))
        self.assertIsNone(pq.pick([{"id": "draft"}], lambda _: False))

    def test_receipt_filename_validation(self):
        self.assertEqual(pq.item_path("jump-second-01"),
                         "render-receipts/jump-second-01.json")
        with self.assertRaises(ValueError):
            pq.item_path("../exploit")
        with self.assertRaises(ValueError):
            pq.item_path("")

if __name__ == "__main__":
    unittest.main()
