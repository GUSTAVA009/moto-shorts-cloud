"""Guardrails for research-only original voice cast, without unauthorized deployment."""
import json
from pathlib import Path
import unittest

CATALOG = Path(__file__).resolve().parents[1] / "voice_cast_candidates.json"


class VoiceCastContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cast = json.loads(CATALOG.read_text(encoding="utf-8"))

    def test_original_cast_is_distinct_and_not_fake_production(self):
        c = self.cast
        self.assertEqual(c["kind"], "research_and_character_specs_only")
        self.assertEqual(c["production_status"], "NOT_DEPLOYED")
        cast = c["proposed_character_voices"]
        self.assertGreaterEqual(len(cast), 12)
        ids = [voice["id"] for voice in cast]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue({"child_cartoon", "comic_bass_cartoon", "medium_warm",
                         "grandpa_biker", "son_teen", "father", "mother"}.issubset(ids))
        for role in cast:
            self.assertEqual(role["status"], "design_spec_only")
            self.assertFalse(role["production_enabled"])
            self.assertTrue(role["requires_original_voice_canary"])
            self.assertTrue(role["requires_russian_asr"])
            self.assertEqual(role["language"], "ru")
            self.assertIn("Original", role["design_prompt_en"][:20].title())

    def test_audition_library_is_not_published_approved(self):
        c = self.cast
        audition = c["available_premade_audition_voices"]
        ids = [item["voice_id"] for item in audition]
        self.assertEqual(len(ids), 21)
        self.assertEqual(len(ids), len(set(ids)))
        for item in audition:
            self.assertFalse(item["production_enabled"])
            self.assertFalse(item["russian_canary_verified"])
            self.assertFalse(item["commercial_rights_for_factory_verified"])
        for role in c["proposed_character_voices"]:
            self.assertTrue(set(role["reference_voice_ids_for_audition"]).issubset(set(ids)))

    def test_owner_may_assign_any_approved_voice_to_any_channel(self):
        p = self.cast["assignment_policy"]
        self.assertTrue(p["any_production_approved_voice_may_be_assigned_to_any_owner_managed_channel"])
        self.assertTrue(p["same_voice_may_be_reused_across_channels"])
        self.assertTrue(p["voice_settings_persist_per_voice_id"])
        self.assertTrue(p["channel_assignment_is_explicit_and_does_not_auto_change_incumbent"])
        self.assertTrue(p["current_gustava_deep_must_not_change_without_owner_voice_approval"])
        self.assertTrue(self.cast["legacy_voice"]["protected"])
        self.assertFalse(p["unlicensed_youtube_voice_extraction_prohibited"] is False)

    def test_narration_duration_not_globally_capped_or_detached_from_visuals(self):
        p = self.cast["assignment_policy"]
        self.assertTrue(p["no_global_tts_narration_duration_limit"])
        self.assertTrue(p["clip_time_and_scene_consistency_must_be_proven_separately"])
        self.assertTrue(p["longer_narration_requires_longer_or_more_licensed_moving_scenes_not_silence_or_loops"])
        self.assertTrue(p["release_requires_actual_russian_test_audio_and_voice_editorial_qa"])


if __name__ == "__main__":
    unittest.main()
