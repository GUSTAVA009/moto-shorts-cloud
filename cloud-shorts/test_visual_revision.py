"""Visual QA repair is bounded and must never bypass historical publication receipts."""
import unittest
from preview_queue import eligible_retry


class VisualRevisionTests(unittest.TestCase):
    def setUp(self):
        self.ep = {"id": "forest-corner-23", "auto_publish": True,
                   "visual_revision_requested": True,
                   "visual_revision_reason": "source_freeze_confirmed"}
        self.receipt = {"id": "forest-corner-23", "state": "preview_ready",
                        "attempt_count": 3, "preview_fingerprint": "old",
                        "voice_qa_passed": True, "mixed_audio_qa_passed": True}

    def test_explicit_new_visuals_allow_one_extra_unpublished_rerender(self):
        self.assertTrue(eligible_retry(self.ep, self.receipt, "fresh-sources"))

    def test_clipped_private_caption_can_be_repaired_once(self):
        self.ep["visual_revision_reason"] = "caption_clipped_confirmed"
        self.ep["auto_publish"] = False
        self.assertTrue(eligible_retry(self.ep, self.receipt, "new-caption-fit"))
        self.assertFalse(eligible_retry(self.ep, self.receipt, "old"))

    def test_fourth_visual_attempt_is_last(self):
        self.receipt["attempt_count"] = 4
        self.assertFalse(eligible_retry(self.ep, self.receipt, "fresh-sources"))

    def test_no_changed_visuals_no_retry(self):
        self.assertFalse(eligible_retry(self.ep, self.receipt, "old"))

    def test_no_confirmed_freeze_no_exception_to_retry_limit(self):
        self.ep["visual_revision_reason"] = "unknown"
        self.assertFalse(eligible_retry(self.ep, self.receipt, "fresh-sources"))

    def test_unreserved_or_invalid_receipt_cannot_retry(self):
        self.receipt["state"] = "reserved"
        self.assertFalse(eligible_retry(self.ep, self.receipt, "fresh-sources"))


if __name__ == "__main__":
    unittest.main()
