"""Regression tests: Buffer must never repeat a Publora or Buffer publication."""
import unittest
import find_pending_buffer as f


class BufferBacklogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"episodes": [
            {"id": "new-original-22", "auto_publish": True,
             "voice_engine": "kokoro_ru_dima",
             "title": "Мотоцикл на сложном подъёме",
             "narration": "Мотоцикл преодолевает поворот на грунтовой трассе.",
             "editorial": {"bike": "offroad-trail-motorcycle"}}]}
        self.receipts = [{"id": "new-original-22", "state": "preview_ready",
                          "voice_qa_passed": True,
                          "mixed_audio_qa_passed": True, "voice_profile": "gustava_male_natural_v4",
                          "male_voice_verified": True, "run_id": "12345"}]
        self.artifacts = [{"name": "daily-preview-new-original-22-12345",
                           "expired": False}]

    def test_approved_unique_original_is_selectable(self):
        item = f.select_for_buffer(self.catalog, self.receipts,
                                   self.artifacts, [])
        self.assertEqual(item[1], "new-original-22")

    def test_buffer_reservation_prevents_duplicate(self):
        item = f.select_for_buffer(self.catalog, self.receipts, self.artifacts,
                                   ["buffer-publication-receipts/new-original-22.json"])
        self.assertIsNone(item)

    def test_old_publora_receipt_prevents_duplicate(self):
        item = f.select_for_buffer(self.catalog, self.receipts, self.artifacts,
                                   ["publication-receipts/new-original-22.json"])
        self.assertIsNone(item)

    def test_unapproved_episode_is_not_selected(self):
        self.catalog["episodes"][0]["auto_publish"] = False
        self.assertIsNone(f.select_for_buffer(
            self.catalog, self.receipts, self.artifacts, []))

    def test_previous_v2_voice_profile_must_not_reenter_buffer(self):
        self.receipts[0]["voice_profile"] = "gustava_male_deep_v2"
        self.assertIsNone(f.select_for_buffer(
            self.catalog, self.receipts, self.artifacts, []))

    def test_old_feminine_timbre_does_not_reenter_buffer(self):
        self.receipts[0].pop("male_voice_verified")
        self.assertIsNone(f.select_for_buffer(
            self.catalog, self.receipts, self.artifacts, []))

    def test_retired_voice_is_not_selected(self):
        self.catalog["episodes"][0]["voice_engine"] = "silero_cis_base_mit"
        self.assertIsNone(f.select_for_buffer(
            self.catalog, self.receipts, self.artifacts, []))

    def test_failed_audio_quality_blocks_selection(self):
        self.receipts[0]["mixed_audio_qa_passed"] = False
        self.assertIsNone(f.select_for_buffer(
            self.catalog, self.receipts, self.artifacts, []))

    def test_expired_preview_artifact_blocks_selection(self):
        self.artifacts[0]["expired"] = True
        self.assertIsNone(f.select_for_buffer(
            self.catalog, self.receipts, self.artifacts, []))


if __name__ == "__main__":
    unittest.main()
