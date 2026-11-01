"""One bounded original Russian ASR fix for an unpublished selfhosted Qwen video."""
import json
from pathlib import Path
import unittest

from editorial_guard import validate_catalog
from render_episode import validate_episode
from preview_queue import eligible_retry, preview_fingerprint

ROOT = Path(__file__).parent
EPISODE = "moto-roadtrip-5b98825cae72"
PRIOR_FP = "7c25d160987e17123d72c8b3175cbb53b6740742b2fed985378521639592e10e"


class ProvenQwenPhoneticFix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / "episodes.json").read_text(encoding="utf-8"))
        cls.ep = next(x for x in cls.catalog["episodes"] if x["id"] == EPISODE)

    def test_exact_real_asr_mismatch_proof_is_attached(self):
        ep = self.ep
        proof = ep["voice_revision_evidence"]
        self.assertEqual(proof["previous_run_id"], "41332576263")
        self.assertEqual(proof["previous_mp4_sha256"],
                         "47350fa4faead044e0b9b948c33e303828e159025110927b75d5199f40a0b937")
        self.assertEqual(proof["previous_wav_sha256"],
                         "8fd80df20fb59dbb8b5cba0d22c6ecb0361a8f55c3319746aac98651c44e25f8")
        self.assertEqual(proof["previous_receipt_attempt_count"], 2)
        self.assertEqual(proof["observed_asr_phrase"], "настоящее гонка")
        self.assertEqual(proof["expected_mispronounced_phrase"], "настоящая гонка")
        self.assertAlmostEqual(proof["previous_raw_asr_coverage"], 0.958)
        self.assertAlmostEqual(proof["previous_mixed_asr_coverage"], 0.958)
        self.assertNotIn("настоящая гонка", ep["narration"])
        self.assertIn("На другом видео — гонка на треке.", ep["narration"])

    def test_private_speaker_and_licensed_scenes_immutable(self):
        ep = self.ep
        self.assertEqual(ep["voice_engine"], "gustava_selfhosted_qwen3")
        self.assertEqual(ep["selfhosted_voice_id"], "gustava-original-v1")
        self.assertFalse(ep["auto_publish"])
        self.assertTrue(ep["auto_preview"])
        self.assertEqual([s["source_page"].split("/")[-2] for s in ep["footage"]],
                         ["epic-motorcycle-journey-through-ladakh-s-mountains-32659157",
                          "motorcycle-racing-on-track-in-indonesia-31894372"])
        self.assertTrue(ep["voice_revision_requested"])
        self.assertFalse(ep["voice_revision_evidence"]["publication_authorized"])
        self.assertTrue(ep["voice_revision_evidence"]["visual_semantic_review_still_required"])
        validate_episode(ep)
        validate_catalog(self.catalog)

    def test_only_one_remaining_fail_closed_private_retry(self):
        ep = self.ep
        receipt = {
            "id": EPISODE, "state": "preview_ready", "attempt_count": 2,
            "run_id": "41332576263", "preview_fingerprint": PRIOR_FP,
            "voice_qa_passed": False, "mixed_audio_qa_passed": False,
            "voice_profile": "gustava_original_qwen3_v1",
        }
        self.assertNotEqual(preview_fingerprint(ep), PRIOR_FP)
        self.assertTrue(eligible_retry(ep, receipt, preview_fingerprint(ep)))
        receipt["attempt_count"] = 3
        self.assertFalse(eligible_retry(ep, receipt, preview_fingerprint(ep)))
        receipt["attempt_count"] = 2
        receipt["state"] = "reserved"
        self.assertFalse(eligible_retry(ep, receipt, preview_fingerprint(ep)))
        receipt["state"] = "preview_ready"
        receipt["voice_qa_passed"] = True
        receipt["mixed_audio_qa_passed"] = True
        self.assertFalse(eligible_retry(ep, receipt, preview_fingerprint(ep)))


if __name__ == "__main__":
    unittest.main()
