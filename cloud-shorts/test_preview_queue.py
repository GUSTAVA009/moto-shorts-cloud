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

    def test_permanent_footage_history_rejects_reused_ids(self):
        import json
        from pathlib import Path
        catalog = json.loads((Path(__file__).parent / "episodes.json").read_text(encoding="utf8"))
        scene = catalog["episodes"][-1]
        first_source = scene["footage"][0]
        from editorial_guard import source_id
        old_id = source_id(first_source)
        history = {"version": 1, "used": {old_id: {"episode": "earlier-video"}}}
        with self.assertRaisesRegex(RuntimeError, "PERMANENT_SOURCE_REUSE_BLOCKED"):
            pq.assert_new_sources(scene, history)
        history["used"][old_id]["episode"] = scene["id"]
        pq.assert_new_sources(scene, history)

    def test_missing_or_corrupt_registry_fails_closed(self):
        with self.assertRaises(RuntimeError):
            pq.decode_history(None)
        with self.assertRaises(RuntimeError):
            pq.decode_history({"sha": "x", "content": ""})

    def test_receipt_filename_validation(self):
        self.assertEqual(pq.item_path("jump-second-01"),
                         "render-receipts/jump-second-01.json")
        with self.assertRaises(ValueError):
            pq.item_path("../exploit")
        with self.assertRaises(ValueError):
            pq.item_path("")

if __name__ == "__main__":
    unittest.main()
