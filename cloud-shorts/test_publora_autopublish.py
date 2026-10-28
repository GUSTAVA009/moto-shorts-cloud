"""No-network tests of fail-closed automatic publication."""
import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest
import publora_autopublish as p


class PubloraAutopublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.video = Path(self.tmp.name) / "test.mp4"
        self.video.write_bytes(b"x" * 500001)
        self.episode = {
            "id": "new-original-22", "auto_publish": True,
            "footage": [{"license": "Pexels License"}]
        }
        self.meta = {"episode_id": self.episode["id"], "title": "Тестовый мото ролик",
                     "description": "Русская озвучка и новые кадры.", "tags": ["мото"]}
        self.qa = {"episode_id": self.episode["id"], "passed": True,
                   "status": "passed", "lexical_coverage": .97, "ending_coverage": 1.0,
                   "final_word_present": True}

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_file_passes_dry_run_without_network(self):
        with patch.object(p, "http", side_effect=AssertionError("No network")):
            result = p.publish(self.episode, self.meta, self.qa, self.video, True)
        self.assertTrue(result["publication_allowed"])
        self.assertEqual(len(result["sha256"]), 64)

    def test_missing_words_block_publication(self):
        self.qa["lexical_coverage"] = .61
        with self.assertRaisesRegex(ValueError, "narration"):
            p.publication_allowed(self.episode, self.meta, self.qa, self.video)

    def test_unapproved_old_episodes_not_published(self):
        self.episode.pop("auto_publish")
        with self.assertRaisesRegex(ValueError, "not explicitly"):
            p.publication_allowed(self.episode, self.meta, self.qa, self.video)

    def test_mismatched_episode_rejected(self):
        self.qa["episode_id"] = "different"
        with self.assertRaisesRegex(ValueError, "mismatch"):
            p.publication_allowed(self.episode, self.meta, self.qa, self.video)

    def test_media_license_guard(self):
        self.episode["footage"][0]["license"] = "Unknown"
        with self.assertRaisesRegex(ValueError, "rights"):
            p.publication_allowed(self.episode, self.meta, self.qa, self.video)

    def test_guard_does_not_contact_api_without_optin(self):
        with patch.dict(p.os.environ, {"PUBLORA_AUTO_PUBLISH_ENABLED": "", "PUBLORA_API_KEY": ""}):
            with patch.object(p, "http", side_effect=AssertionError("No network")):
                result = p.publish(self.episode, self.meta, self.qa, self.video)
        self.assertIn("PUBLORA_AUTO_PUBLISH_ENABLED", result["skipped"])

    def test_receipt_slug_traversal_rejected(self):
        with self.assertRaises(ValueError):
            p.receipt_path("../other")


if __name__ == "__main__":
    unittest.main()
