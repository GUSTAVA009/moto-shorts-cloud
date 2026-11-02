"""Fresh Pexels source supply: never recycle consumed footage or bypass publishing review."""
import json
from pathlib import Path
import os
import unittest
from unittest.mock import patch

from moto_assets import validated_media, source_id
from moto_autocreate import ROOT, create_one
from source_story import scene_for, select_pair, compose, require_filmable

NEW_IDS = {"12990227", "34948751", "5206883", "4475335", "36705180", "40373652", "9607287", "9607279"}


class AutonomousFootageRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pool = json.loads((ROOT / "verified_pexels_pool.json").read_text("utf8"))["sources"]
        cls.catalog = json.loads((ROOT / "episodes.json").read_text("utf8"))
        cls.new = {source_id(s): s for s in cls.pool if source_id(s) in NEW_IDS}

    def test_new_sources_are_unique_and_not_reused_across_episodes(self):
        source_users = {}
        for episode in self.catalog["episodes"]:
            for src in episode["footage"]:
                source_users.setdefault(source_id(src), []).append(episode["id"])
        self.assertEqual(set(self.new), NEW_IDS)
        # The autonomous factory has already consumed some newly supplied stock:
        # it is an error to insist that LIVE catalogs stay pre-consumption forever.
        self.assertTrue(NEW_IDS.intersection(source_users))
        for source_id_value in NEW_IDS:
            self.assertLessEqual(len(source_users.get(source_id_value, [])), 1)
        self.assertEqual(len(self.pool), len({source_id(x) for x in self.pool}))
        for clip in self.new.values():
            self.assertEqual(validated_media(clip), source_id(clip))
            self.assertTrue(clip["author"].strip())
            self.assertEqual(clip["license"], "Pexels License")
            self.assertGreaterEqual(clip["duration"], 9)
            self.assertNotIn("reviewed_mp4_sha256", clip)

    def test_source_titles_ground_two_new_non_generic_actions(self):
        self.assertEqual(scene_for(self.new["36705180"])[0], "inflation")
        self.assertEqual(scene_for(self.new["9607287"])[0], "stunt")
        self.assertEqual(scene_for(self.new["9607279"])[0], "stunt")
        self.assertEqual(scene_for(self.new["12990227"])[0], "race")
        self.assertEqual(scene_for(self.new["34948751"])[0], "motor")
        self.assertEqual(scene_for(self.new["5206883"])[0], "city")
        self.assertEqual(scene_for(self.new["4475335"])[0], "ride")
        for a, b in (("36705180", "34948751"), ("12990227", "9607287"), ("5206883", "4475335")):
            pair = select_pair([self.new[a], self.new[b]], set())
            self.assertEqual(len(pair), 2)
            self.assertNotEqual(pair[0]["author"].casefold(), pair[1]["author"].casefold())
            story = compose(pair, [])
            self.assertEqual(len(require_filmable(story, pair)), 2)

    def test_two_private_episodes_can_be_created_without_external_keys(self):
        catalog = json.loads(json.dumps(self.catalog))
        # Freeze the deterministic *pre-autofill* fixture, not the live
        # historical ledger that advances after this test helped unblock it.
        baseline = next(i for i, ep in enumerate(catalog["episodes"])
                        if ep["id"] == "moto-city-2ed049c15ee1")
        catalog["episodes"] = catalog["episodes"][:baseline + 1]
        with patch.dict(os.environ, {
            "PEXELS_API_KEY": "", "OPENAI_API_KEY": "",
            "OPENROUTER_API_KEY": "", "GUSTAVA_TTS_PROVIDER": "gustava_selfhosted_qwen3",
        }), patch("moto_autocreate.commons_results", return_value=[]):
            built = []
            for _ in range(2):
                ep = create_one(catalog, source_fetch=lambda *args: [],
                                commons_fetch=lambda *args: [])
                self.assertIs(ep["auto_publish"], False)
                self.assertIs(ep["auto_preview"], True)
                self.assertEqual(ep["voice_engine"], "gustava_selfhosted_qwen3")
                self.assertEqual(len(ep["footage"]), 2)
                self.assertFalse({source_id(s) for s in ep["footage"]}.intersection(
                    {source_id(s) for old in catalog["episodes"] for s in old["footage"]}))
                catalog["episodes"].append(ep)
                built.append(ep["id"])
            self.assertEqual(len(set(built)), 2)


if __name__ == "__main__":
    unittest.main()
