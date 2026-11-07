"""Regression guards for the original serialized Shorts production brief."""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from storyverse import StoryverseError, load_series, plan_episode, next_unproduced_concept, validate_series

class StoryverseTest(unittest.TestCase):
    def setUp(self):
        self.series = load_series()

    def test_full_pilot_has_19_original_causal_scenes(self):
        scenes = self.series["pilot"]["shots"]
        self.assertEqual(len(scenes), 19)
        self.assertEqual(scenes[0]["start_sec"], 0)
        self.assertEqual(scenes[-1]["end_sec"], 114)
        self.assertEqual(len({s["visual_action_ru"] for s in scenes}), 19)
        self.assertTrue(any("дет" in s["narration_ru"].lower() for s in scenes))
        self.assertTrue(any("верёвк" in s["narration_ru"].lower() for s in scenes))
        self.assertTrue(any("выбрались" in s["narration_ru"].lower() for s in scenes))
        self.assertTrue(any("сосед" in s["visual_action_ru"].lower() or "напротив" in s["visual_action_ru"].lower() for s in scenes))

    def test_reference_is_not_source_media(self):
        self.assertIn("no_source_media", self.series["reference_use"])
        self.assertTrue(self.series["publish_contract"]["no_reference_frames_or_audio"])
        self.assertTrue(self.series["visual_style"]["always_original_characters"])
        self.assertNotIn("reference_for_analysis.mp4", json.dumps(self.series))

    def test_owner_voice_locked_no_fallback(self):
        self.assertEqual(self.series["voice_contract"]["voice_id"], "deep")
        self.assertTrue(self.series["voice_contract"]["fallback_forbidden"])
        bad = copy.deepcopy(self.series)
        bad["voice_contract"]["voice_id"] = "silero"
        with self.assertRaises(StoryverseError):
            validate_series(bad)

    def test_not_a_published_video(self):
        plan = plan_episode(self.series)
        self.assertEqual(plan["job_type"], "creative_brief_not_rendered")
        self.assertEqual(plan["production_execution_status"], "NOT_STARTED")
        self.assertNotIn("mp4_url", plan)
        self.assertTrue(plan["publish_contract"]["do_not_publish_creative_brief"])

    def test_invalid_scene_count_fails_closed(self):
        bad = copy.deepcopy(self.series)
        bad["pilot"]["shots"].pop()
        with self.assertRaisesRegex(StoryverseError, "nineteen"):
            validate_series(bad)

    def test_invalid_timing_fails_closed(self):
        bad = copy.deepcopy(self.series)
        bad["pilot"]["shots"][5]["end_sec"] = 38
        with self.assertRaisesRegex(StoryverseError, "Timing"):
            validate_series(bad)

    def test_missing_scene_action_rejected(self):
        bad = copy.deepcopy(self.series)
        bad["pilot"]["shots"][4]["visual_action_ru"] = ""
        with self.assertRaisesRegex(StoryverseError, "visual_action_ru"):
            validate_series(bad)

    def test_story_bank_is_diverse_and_selectable(self):
        names = [x["title"] for x in self.series["episodes"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(next_unproduced_concept(self.series)["episode_id"], "02")
        self.assertEqual(next_unproduced_concept(self.series, {"02"})["episode_id"], "03")

    def test_outline_does_not_masquerade_as_renderable(self):
        with self.assertRaisesRegex(StoryverseError, "Outline only"):
            plan_episode(self.series, "02")

    def test_silent_characters_and_locked_sprites_mandatory(self):
        self.assertTrue(self.series["visual_style"]["characters_do_not_speak"])
        self.assertTrue(self.series["visual_style"]["mouth_animation_forbidden"])
        self.assertTrue(self.series["voice_contract"]["voice_is_offscreen_narrator_only"])
        self.assertTrue(self.series["publish_contract"]["require_qa_no_facial_morphs"])
        bad = copy.deepcopy(self.series)
        bad["visual_style"]["mouth_animation_forbidden"] = False
        with self.assertRaisesRegex(StoryverseError, "Silent stable-character"):
            validate_series(bad)

    def test_uncanny_faces_are_forbidden_and_visual_rejection_blocks_release(self):
        self.assertTrue(self.series["visual_style"]["giant_fixed_staring_eyes_forbidden"])
        self.assertTrue(self.series["visual_style"]["blank_doll_like_expressions_forbidden"])
        self.assertTrue(self.series["publish_contract"]["owner_rejected_uncanny_visuals_block_future_uploads"])
        bad = copy.deepcopy(self.series)
        bad["visual_style"]["uncanny_valley_faces_forbidden"] = False
        with self.assertRaisesRegex(StoryverseError, "No creepy character design"):
            validate_series(bad)

    def test_format_specific(self):
        vid = self.series["production_format"]
        self.assertEqual((vid["resolution"], vid["fps"], vid["duration_seconds"]), ("1080x1920", 30, 114))
        self.assertIn("caption", vid["subtitles"].lower())
        self.assertTrue(self.series["narrative_contract"]["has_payoff"])
        self.assertTrue(self.series["narrative_contract"]["cliffhanger_allowed_only_after_payoff"])

if __name__ == "__main__":
    unittest.main()
