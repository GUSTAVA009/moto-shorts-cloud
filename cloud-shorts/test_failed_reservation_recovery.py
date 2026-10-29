"""Ensure reserved pipeline crashes cannot silently become duplicate video uploads."""
import unittest
from preview_queue import eligible_abandoned_source_retry


class AbandonedReservationTests(unittest.TestCase):
    def setUp(self):
        self.ep = {"id": "night-traffic-27",
                   "source_revision_requested": True,
                   "source_revision_reason": "oversized_source_replaced"}
        self.receipt = {"id": "night-traffic-27", "state": "reserved",
                        "attempt_count": 1, "preview_fingerprint": "original-sources",
                        "run_id": "40929639066"}

    def test_explicit_replacement_and_verified_failure_allows_one_retry(self):
        self.assertTrue(eligible_abandoned_source_retry(
            self.ep, self.receipt, "smaller-licensed-video", "failure"))

    def test_no_retry_while_run_still_running(self):
        self.assertFalse(eligible_abandoned_source_retry(
            self.ep, self.receipt, "new", "in_progress"))

    def test_no_retry_without_media_replacement(self):
        self.assertFalse(eligible_abandoned_source_retry(
            self.ep, self.receipt, "original-sources", "failure"))

    def test_no_retry_on_unapproved_reason(self):
        self.ep["source_revision_reason"] = "changed_my_mind"
        self.assertFalse(eligible_abandoned_source_retry(
            self.ep, self.receipt, "new", "failure"))

    def test_no_retry_after_attempt_limit(self):
        self.receipt["attempt_count"] = 3
        self.assertFalse(eligible_abandoned_source_retry(
            self.ep, self.receipt, "new", "failure"))

    def test_no_retry_when_receipt_is_publishable(self):
        self.receipt["state"] = "preview_ready"
        self.assertFalse(eligible_abandoned_source_retry(
            self.ep, self.receipt, "new", "failure"))


if __name__ == "__main__":
    unittest.main()
