"""No-network tests: source-grounded auto factory can film ride/ride terrain lesson."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from moto_autocreate import create_one,native_source_candidates
from source_story import scene_for,select_pair,require_filmable,grounded_surface_microguide
from source_action_evidence import verified_riding_context
from moto_assets import source_id


HERE=Path(__file__).resolve().parent


class GroundedTerrainShortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=json.loads((HERE/"episodes.json").read_text(encoding="utf8"))
        cls.pool=json.loads((HERE/"verified_pexels_pool.json").read_text(encoding="utf8"))["sources"]
        cls.by_id={source_id(s):s for s in cls.pool}

    def test_all_six_free_real_riding_environments_from_sha_frames(self):
        expected={"5803517":"sand","5207054":"city","28332401":"road",
                  "31901418":"garage","5803627":"trail","5198992":"alley"}
        for id,terrain in expected.items():
            with self.subTest(id=id):
                s=self.by_id[id]
                self.assertEqual(verified_riding_context(s),terrain)
                # The planner never blindly trusts an authored context.
                fake=dict(s,verified_riding_context="sand")
                if terrain!="sand":
                    self.assertNotEqual(scene_for(fake)[0],"ride_sand")

    def test_terrain_pairs_need_distinct_proved_environments_and_creators(self):
        with patch.dict(os.environ,{"GUSTAVA_SOURCE_ACTION_EVIDENCE_REQUIRED":"1"}):
            clips=native_source_candidates([
                self.by_id["5207054"],self.by_id["31901418"]])
            self.assertEqual(select_pair(clips,set()),[])
            clips=native_source_candidates([
                self.by_id["5803627"],self.by_id["28332401"]])
            self.assertEqual(len(select_pair(clips,set())),2)

    def test_original_grounded_story_is_not_generic_ab_competition(self):
        with patch.dict(os.environ,{"GUSTAVA_SOURCE_ACTION_EVIDENCE_REQUIRED":"1"}):
            clips=native_source_candidates([
                self.by_id["5803627"],self.by_id["28332401"]])
            result=grounded_surface_microguide(clips,[],0,[])
        self.assertIn("лесной тропе",result["narration"])
        self.assertIn("асфальтированной дороге",result["narration"])
        self.assertIn("темп",result["narration"])
        self.assertNotIn("что тебе ближе",result["narration"].lower())
        self.assertEqual(len(require_filmable(result,clips)),2)
        self.assertEqual(result["_editorial_format"],"original_action_microguide_v1")

    def test_real_factory_recovers_exact_new_private_script_without_source_reuse(self):
        # Recreate the stock window BEFORE this proven terrain pair was
        # reserved in the immutable catalog. Once reserved, the real planner
        # must correctly refuse reusing its footage, not falsely claim it is
        # another brand-new episode.
        previous=dict(self.catalog,episodes=[
            x for x in self.catalog["episodes"]
            if x["id"]!="moto-racing-1a27db9dcf31"])
        with patch.dict(os.environ,{
                "GUSTAVA_NATIVE_SOURCE_ONLY":"1",
                "GUSTAVA_SOURCE_ACTION_EVIDENCE_REQUIRED":"1",
                "GUSTAVA_EXPORT_PROFILE":"2k",
                "PEXELS_API_KEY":""}):
            ep=create_one(previous,commons_fetch=lambda _:[])
            with self.assertRaisesRegex(RuntimeError,
                    "NO_NEW_ACTION_MATCHING_LICENSED_MOTO_CLIPS"):
                create_one(self.catalog,commons_fetch=lambda _:[])
        old={source_id(s) for x in previous["episodes"]
             for s in x["footage"]}
        self.assertTrue(all(source_id(s) not in old for s in ep["footage"]))
        self.assertEqual(ep["editorial_format"],"original_action_microguide_v1")
        self.assertIs(ep["auto_preview"],True)
        self.assertIs(ep["auto_publish"],False)
        self.assertEqual({x["verified_riding_context"] for x in ep["footage"]},
                         {"trail","road"})

    def test_forged_sha_cannot_create_context(self):
        good=self.by_id["5803627"]
        forged=dict(good,native_4k_sha256="0"*64,
                    verified_riding_context="trail")
        self.assertIsNone(verified_riding_context(forged))
        self.assertNotEqual(scene_for(forged)[0],"ride_trail")


if __name__=="__main__":
    unittest.main()
