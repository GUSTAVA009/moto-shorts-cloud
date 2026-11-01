"""Regression tests for evidence-backed speech-first mix and editorial accuracy."""
from __future__ import annotations
import json
from pathlib import Path
import unittest

from render_episode import validated_clean_speech_intro_seconds, validate_episode
from preview_queue import eligible_retry
from source_story import require_filmable, touring_track_myth

HERE = Path(__file__).resolve().parent
ID = "moto-roadtrip-5b98825cae72"
PREV_SHA = "68ed361b2d2b6936cfe224eb7072b3896b2c005b205f8c349bef487038191b86"
NEW_TEXT = ("Горная дорога или трек? На первом видео райдер путешествует среди гор. "
            "На втором — мотоциклист едет по треку. Две разные поездки. Что ближе тебе?")


class PrivateMixedAudioEditorialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalog = json.loads((HERE / "episodes.json").read_text(encoding="utf8"))
        cls.source_episode = next(ep for ep in catalog["episodes"] if ep["id"] == ID)

    def revised_episode(self):
        ep = dict(self.source_episode)
        ep["narration"] = NEW_TEXT
        ep["auto_preview"] = True
        ep["auto_publish"] = False
        ep["clean_speech_intro_seconds"] = 3.3
        ep["mixed_editorial_revision_requested"] = True
        ep["mixed_editorial_revision_reason"] = "actual_final_mix_asr_and_visual_truth_fix"
        ep["mixed_editorial_revision_evidence"] = {
            "prior_run_id": "41333288738",
            "prior_mp4_sha256": PREV_SHA,
            "prior_raw_asr_coverage": 1.0,
            "prior_mixed_asr_coverage": 0.957,
            "source_ids": ["32659157", "31894372"],
            "publication_authorized": False
        }
        return ep

    def receipt(self):
        return {"id": ID, "state": "preview_ready",
                "run_id": "41333288738", "attempt_count": 3,
                "preview_fingerprint": "prior-hash",
                "voice_profile": "gustava_original_qwen3_v1",
                "voice_qa_passed": True,
                "mixed_audio_qa_passed": False}

    def test_speech_first_intro_is_bounded_and_validated(self):
        self.assertEqual(validated_clean_speech_intro_seconds("3.3"), 3.3)
        self.assertEqual(validated_clean_speech_intro_seconds(0), 0)
        for value in (-1, 4.01, "nan", "inf"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validated_clean_speech_intro_seconds(value)
        self.assertEqual(validate_episode(self.revised_episode()), ID)

    def test_two_real_footage_sources_allow_truthful_track_without_fake_race(self):
        ep = self.revised_episode()
        self.assertEqual(require_filmable(ep, ep["footage"]), ["touring", "race"])
        self.assertIn("мотоциклист едет по треку", ep["narration"])
        self.assertNotIn("гонка на треке", ep["narration"])

    def test_future_generated_mythism_does_not_fabricate_race_competitors(self):
        ep = self.revised_episode()
        draft = touring_track_myth(ep["footage"], previous_titles=[])
        self.assertNotIn("мотоциклисты участвуют в гонке", draft["narration"])
        self.assertIn("мотоциклист едет по треку", draft["narration"])
        self.assertIn("поездка по треку", draft["description"])

    def test_exact_final_artifact_allows_one_more_private_render(self):
        ep = self.revised_episode()
        self.assertTrue(eligible_retry(ep, self.receipt(), "genuinely-new-fingerprint"))
        self.assertFalse(eligible_retry(ep, self.receipt(), "prior-hash"))

    def test_no_unknown_audio_or_public_video_may_reuse_exception(self):
        ep = self.revised_episode()
        rec = self.receipt()
        cases = [
            (dict(ep, auto_publish=True), rec),
            (dict(ep, voice_engine="kokoro_ru_dima"), rec),
            (dict(ep, id="someone-else"), rec),
            (dict(ep, narration="гонка на треке"), rec),
            (dict(ep, mixed_editorial_revision_evidence=dict(
                ep["mixed_editorial_revision_evidence"], prior_mp4_sha256="0" * 64)), rec),
            (ep, dict(rec, attempt_count=4)),
            (ep, dict(rec, run_id="41332576263")),
            (ep, dict(rec, mixed_audio_qa_passed=True)),
            (ep, dict(rec, state="reserved")),
        ]
        for newep, receipt in cases:
            with self.subTest(newep=newep.get("id"), receipt=receipt):
                self.assertFalse(eligible_retry(newep, receipt, "genuinely-new-fingerprint"))


if __name__ == "__main__":
    unittest.main()
