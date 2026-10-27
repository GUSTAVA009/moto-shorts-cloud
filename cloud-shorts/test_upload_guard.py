"""Offline tests; no YouTube or GitHub writes."""
import unittest
import upload_guard as guard


class GateTests(unittest.TestCase):
    def test_ledger_key_unique_by_channel_and_hash(self):
        h = "a" * 64
        c1 = "UC" + "1" * 22
        c2 = "UC" + "2" * 22
        self.assertEqual(guard.ledger_path(c1, h),
                         "upload-receipts/" + c1 + "/" + h + ".json")
        self.assertNotEqual(guard.ledger_path(c1, h), guard.ledger_path(c2, h))

    def test_reject_bad_channels(self):
        with self.assertRaises(ValueError):
            guard.ledger_path("other", "b" * 64)
        with self.assertRaises(ValueError):
            guard.ledger_path("UC" + "1" * 22, "../bad")

    def test_reservation_initially_blocks_retries(self):
        c = "UC" + "Z" * 22
        a = guard.make_reservation(c, "f" * 64, "12345")
        self.assertEqual(a["status"], "reserved")
        self.assertEqual(a["channel_id"], c)
        self.assertNotIn("client_secret", a)
        self.assertNotIn("refresh_token", a)

    def test_receipt_consistency(self):
        c = "UC" + "1" * 22
        sha = "a" * 64
        res = guard.make_reservation(c, sha, "23")
        video_id = "abcdefghijk"
        receipt = {"sha256": sha, "channel_id": c, "video_id": video_id}
        self.assertEqual(guard.validate_receipt(res, receipt), video_id)
        with self.assertRaises(ValueError):
            guard.validate_receipt(res, dict(receipt, channel_id="UC" + "2"*22))
        with self.assertRaises(ValueError):
            guard.validate_receipt(res, dict(receipt, video_id="NOT_AN_ID_TOO_LONG"))

    def test_token_required_in_live_mode(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}):
            with self.assertRaises(RuntimeError):
                guard.headers()

if __name__ == "__main__":
    unittest.main()
