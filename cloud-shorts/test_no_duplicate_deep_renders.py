"""Prevent re-rendering approved original GUSTAVA DEEP narration for a mere code change."""
import unittest
import preview_queue as q


class DeepPreviewDedupTests(unittest.TestCase):
    def episode(self, source="b"):
        return {
            "id": "moto-rain-example",
            "auto_preview": True,
            "auto_publish": False,
            "voice_engine": "aidocmaker_deep",
            "voice_profile": "gustava_create_audio_deep_v1",
            "voice_revision_requested": True,
            "deep_audio": {"source_audio_sha256": source * 64},
        }

    def receipt(self, source="a"):
        return {
            "id": "moto-rain-example",
            "state": "preview_ready",
            "attempt_count": 1,
            "preview_fingerprint": "old-render",
            "voice_profile": "gustava_create_audio_deep_v1",
            "voice_qa_passed": True,
            "mixed_audio_qa_passed": True,
            "deep_source_sha256": source * 64,
        }

    def test_master_code_change_does_not_rerender_same_audio(self):
        ep = self.episode("a")
        self.assertFalse(q.eligible_retry(ep, self.receipt("a"), "new-code-master"))

    def test_legacy_receipt_without_audio_proof_fails_closed(self):
        receipt = self.receipt()
        receipt.pop("deep_source_sha256")
        self.assertFalse(q.eligible_retry(self.episode(), receipt, "new-code-master"))

    def test_explicit_new_original_deep_mp3_may_rerender_unpublished(self):
        self.assertTrue(q.eligible_retry(self.episode(), self.receipt(), "new-voice-file"))
        changed = self.episode()
        changed["auto_publish"] = True
        self.assertFalse(q.eligible_retry(changed, self.receipt(), "new-voice-file"))

    def test_invalid_hash_cannot_trigger_rerender(self):
        ep = self.episode("x")
        self.assertFalse(q.eligible_retry(ep, self.receipt(), "new-code"))
        receipt = self.receipt()
        receipt["deep_source_sha256"] = "bad"
        self.assertFalse(q.eligible_retry(self.episode(), receipt, "new-code"))

    def test_exhausted_preview_attempts_cannot_rerender(self):
        receipt = self.receipt()
        receipt["attempt_count"] = q.MAX_ATTEMPTS
        self.assertFalse(q.eligible_retry(self.episode(), receipt, "new-source"))

    def test_without_voice_revision_no_rerender(self):
        ep = self.episode()
        ep["voice_revision_requested"] = False
        self.assertFalse(q.eligible_retry(ep, self.receipt(), "changed-code"))


if __name__ == "__main__":
    unittest.main()
