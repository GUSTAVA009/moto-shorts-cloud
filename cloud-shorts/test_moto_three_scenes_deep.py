"""Original motorbike life pilot: honest three distinct Pexels actions and exact DEEP preset."""
import copy
import json
from pathlib import Path
import unittest

from deep_voice import VOICE_ENGINE
from editorial_guard import validate_catalog
from editorial_novelty import require_novel_visual_story
from render_episode import validate_episode
from visual_director import directed_plan, verify_scene_script_anchors

CATALOG = json.loads((Path(__file__).parent / "episodes.json").read_text("utf8"))
SLUG = "moto-moto-life-three-scenes-deep-20261030"


def episode():
    return next(e for e in CATALOG["episodes"] if e["id"] == SLUG)


class OriginalThreeScenesTests(unittest.TestCase):
    def test_full_catalog_licensed_source_and_editorial_integrity(self):
        self.assertGreaterEqual(validate_catalog(CATALOG)["episodes"], 43)
        self.assertEqual(validate_episode(episode()), SLUG)
        self.assertEqual(episode()["voice_engine"], VOICE_ENGINE)
        self.assertFalse(episode()["auto_publish"])

    def test_three_separate_provider_identified_actions_not_repeated_stock(self):
        ep = episode()
        sources = ep["footage"]
        self.assertEqual(len(sources), 3)
        self.assertEqual(len({s["author"] for s in sources}), 3)
        ids = [s["source_page"].split("-")[-1].strip("/") for s in sources]
        self.assertEqual(ids, ["5450253", "8551066", "9607278"])
        self.assertEqual(verify_scene_script_anchors(ep),
                         ["clip_0", "clip_1", "clip_2"])
        require_novel_visual_story(ep, CATALOG["episodes"][:-1])

    def test_ordered_footage_covers_speech_without_stills_or_repeats(self):
        ep = episode()
        plan = directed_plan(ep, {"clip_0": 12, "clip_1": 13, "clip_2": 24}, 20.5)
        self.assertEqual([p["source"] for p in plan], ["clip_0", "clip_1", "clip_2"])
        self.assertEqual(len({x["source"] for x in plan}), 3)
        self.assertGreaterEqual(sum(x["seconds"] for x in plan), 20.4)
        self.assertTrue(all(x["seconds"] >= 3.3 for x in plan))

    def test_wrong_visual_action_or_script_order_is_rejected(self):
        ep = copy.deepcopy(episode())
        ep["scene_script_anchors"][1]["source"] = "clip_2"
        with self.assertRaisesRegex(ValueError, "VISUAL_BEATS_OFF_SCRIPT"):
            verify_scene_script_anchors(ep)
        ep = copy.deepcopy(episode())
        ep["scene_script_anchors"][1]["spoken_anchor"] = "Что ближе тебе"
        with self.assertRaisesRegex(ValueError, "VISUAL_BEATS_OFF_SCRIPT"):
            verify_scene_script_anchors(ep)


if __name__ == "__main__":
    unittest.main()
