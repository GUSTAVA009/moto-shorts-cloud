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

    def test_revised_unpublished_audio_may_retry_but_only_three_attempts(self):
        episode = {"id": "motorcycle-serial-01", "auto_preview": True}
        bad = {"id": episode["id"], "state": "preview_ready",
               "attempt_count": 1, "preview_fingerprint": "old-script",
               "voice_qa_passed": False, "mixed_audio_qa_passed": False}
        self.assertTrue(pq.eligible_retry(episode, bad, "revised-script"))
        self.assertFalse(pq.eligible_retry(episode, bad, "old-script"))
        bad["state"] = "reserved"
        self.assertFalse(pq.eligible_retry(episode, bad, "revised-script"))
        bad["state"] = "preview_ready"
        bad["attempt_count"] = 3
        self.assertFalse(pq.eligible_retry(episode, bad, "revised-script"))

    def test_successful_audio_preview_is_never_remade(self):
        ep = {"id": "motorcycle-serial-02"}
        record = {"id": ep["id"], "state": "preview_ready",
                  "voice_qa_passed": True, "mixed_audio_qa_passed": True,
                  "attempt_count": 1, "preview_fingerprint": "past"}
        self.assertFalse(pq.eligible_retry(ep, record, "future"))

    def test_modified_script_changes_fingerprint(self):
        ep = {"id": "new-test-01", "narration": "Первое путешествие"}
        a = pq.preview_fingerprint(ep)
        ep["narration"] = "Второе путешествие"
        b = pq.preview_fingerprint(ep)
        self.assertNotEqual(a, b)
        self.assertEqual(len(a), 64)

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
