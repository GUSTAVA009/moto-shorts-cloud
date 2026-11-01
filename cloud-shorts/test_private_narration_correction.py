"""Regression: public narration must correspond to visually inspected action.

The first 11.63s private QA-passed MP4 showed the rider struggling in mud,
not riding. Do not silently reuse that narration or its recording.
"""
import json
from pathlib import Path
import unittest

from visual_director import verify_scene_script_anchors, directed_plan

ROOT=Path(__file__).resolve().parent

class VisuallyGroundedNarrationTests(unittest.TestCase):
    def test_new_private_replacement_describes_actual_scenes_and_retains_evidence(self):
        obj=json.loads((ROOT/"episodes.json").read_text("utf8"))
        ep=next(x for x in obj["episodes"]
                if x["id"]=="moto-racing-mud-contrast-20261101")
        old=ep["deep_audio_revision_history"][0]
        self.assertTrue(old["prior_video_private_not_published"])
        self.assertRegex(old["prior_deep_source_sha256"],r"^[0-9a-f]{64}$")
        self.assertEqual(old["prior_render_run_id"],"41293506062")
        self.assertIn("райдер едет по",old["prior_narration"])
        self.assertIn("девушка на байке застряла в глубокой грязи",ep["narration"])
        self.assertNotIn("райдер едет по",ep["narration"])
        self.assertEqual(verify_scene_script_anchors(ep),["clip_0","clip_1"])
        self.assertEqual([b["action"] for b in ep["scene_script_anchors"]],
                         ["motorcycle_drag_race","motorcycle_muddy_offroad"])
        self.assertTrue(ep["align_middle_caption_to_second_scene"])
        if ep.get("deep_audio"):
            self.assertNotEqual(ep["deep_audio"]["source_audio_sha256"],
                                old["prior_deep_source_sha256"])

    def test_single_inbox_record_matches_new_script_not_old_private_audio(self):
        obj=json.loads((ROOT/"episodes.json").read_text("utf8"))
        ep=next(x for x in obj["episodes"]
                if x["id"]=="moto-racing-mud-contrast-20261101")
        bank=json.loads((ROOT/"deep-voice-inbox-20261101.json").read_text("utf8"))
        matches=[r for r in bank["records"] if r["episode_id"]==ep["id"]]
        self.assertEqual(len(matches),1)
        self.assertEqual(matches[0]["narration"],ep["narration"])
        self.assertEqual(matches[0]["voice_id"],"deep")
        self.assertEqual(matches[0]["provider"],"aidocmaker.com")
        self.assertNotEqual(matches[0]["context_id"],
                            ep["deep_audio_revision_history"][0]["prior_audio_context_id"])

if __name__=="__main__":
    unittest.main()
