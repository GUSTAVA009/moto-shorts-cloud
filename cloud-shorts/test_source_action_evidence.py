"""No-network production regressions: actual source frames outrank titles."""
from copy import deepcopy
import json
from pathlib import Path
import os
from unittest.mock import patch
import unittest
from source_action_evidence import (
    load_evidence,source_dynamic_action_verified,require_episode_dynamic_sources)
from native_source_preflight import require_native_sources
from moto_autocreate import native_source_candidates

HERE=Path(__file__).resolve().parent


class FactoryMotionSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pool=json.loads((HERE/"verified_pexels_pool.json").read_text(
            encoding="utf8"))["sources"]
        cls.evidence=load_evidence()

    def test_all_37_sources_have_sha_pinned_evidence_and_16_confirmed_moving(self):
        sources=[s for s in self.pool
                 if (s.get("native_4k_sha256") or s.get("native_2k_sha256"))
                 and s["url"].rstrip("/").split("/")[-1] in self.evidence]
        self.assertEqual(len(sources),37)
        approved=[s for s in sources if source_dynamic_action_verified(
            s,self.evidence)]
        self.assertEqual(len(approved),16)
        # Provenance alone does not make a parked bike a riding action.
        self.assertEqual(len(sources)-len(approved),21)

    def test_three_previous_broken_mp4_sources_cannot_get_action_preflight(self):
        catalog=json.loads((HERE/"episodes.json").read_text(encoding="utf8"))
        ids={"moto-city-9561eabb9e24",
             "moto-roadtrip-83f0461a1801",
             "moto-helmet-3368471b0f59"}
        for episode in catalog["episodes"]:
            if episode["id"] not in ids:continue
            with self.subTest(id=episode["id"]):
                expected=("SOURCE_VISUAL_UNVERIFIED_TRAFFIC_CLAIM"
                          if episode["id"]=="moto-roadtrip-83f0461a1801"
                          else "SOURCE_VISUAL_ACTUAL_RIDING_NOT_PROVEN")
                with self.assertRaisesRegex(ValueError,expected):
                    require_episode_dynamic_sources(episode,self.evidence)

    def test_tampered_model_or_sha_or_frames_or_evidence_is_never_approved(self):
        good=next(s for s in self.pool
                  if s["url"].rstrip("/").endswith("35963831"))
        self.assertTrue(source_dynamic_action_verified(good,self.evidence))
        bad_source=dict(good,native_4k_sha256="0"*64)
        self.assertFalse(source_dynamic_action_verified(bad_source,self.evidence))
        sid="35963831"
        for field,invalid in (("model","qwen3.5:other"),
                              ("action","standing"),
                              ("motorcycle_visible",False),
                              ("confidence",0.91),
                              ("action_visually_confirmed",False),
                              ("frame_sha256",["f"*64])):
            broken=deepcopy(self.evidence)
            broken[sid][field]=invalid
            self.assertFalse(source_dynamic_action_verified(good,broken),
                             field)

    def test_new_2k_jump_is_proven_from_real_frames_not_page_title(self):
        from source_story import scene_for
        jump=next(s for s in self.pool if s["url"].endswith("/26447454/"))
        self.assertTrue(source_dynamic_action_verified(jump,self.evidence))
        self.assertEqual(scene_for(jump)[0],"jump")
        forged=dict(jump,native_2k_sha256="0"*64)
        self.assertFalse(source_dynamic_action_verified(forged,self.evidence))
        self.assertNotEqual(scene_for(forged)[0],"jump")

    def test_original_factory_auto_selects_unused_different_motorcycle_actions(self):
        from moto_autocreate import create_one
        data=json.loads((HERE/"episodes.json").read_text(encoding="utf8"))
        # Reproduce the pre-production stock window, even after this first
        # validated candidate has been reserved in the immutable catalog.
        data["episodes"]=[ep for ep in data["episodes"]
                          if ep["id"]!="moto-roadtrip-153fe6130270"]
        with patch.dict(os.environ,{
                "GUSTAVA_NATIVE_SOURCE_ONLY":"1",
                "GUSTAVA_SOURCE_ACTION_EVIDENCE_REQUIRED":"1",
                "GUSTAVA_EXPORT_PROFILE":"2k",
                "PEXELS_API_KEY":""}):
            ep=create_one(data,commons_fetch=lambda _:[])
        used={x["url"].rstrip("/").split("/")[-1] for x in ep["footage"]}
        self.assertIn("26447454",used)
        self.assertNotIn("5803517",used)
        self.assertIn(ep["editorial_format"],(
            "source_anchored_action_contrast","original_action_microguide_v1"))
        self.assertIs(ep["auto_publish"],False)

    def test_autonomous_script_stock_excludes_ungrounded_footage(self):
        with patch.dict(os.environ,{
               "GUSTAVA_SOURCE_ACTION_EVIDENCE_REQUIRED":"1"}):
            selected=native_source_candidates(self.pool,"2k")
            self.assertEqual(len(selected),16)
            self.assertTrue(all(source_dynamic_action_verified(s)
                                for s in selected))
            self.assertFalse(any(x["url"].endswith("/5806214/")
                                 for x in selected))
        with patch.dict(os.environ,{
               "GUSTAVA_SOURCE_ACTION_EVIDENCE_REQUIRED":"0"}):
            selected=native_source_candidates(self.pool,"2k")
            self.assertGreater(len(selected),16)

    def test_eligible_episode_still_needs_two_native_sources_and_action_proof(self):
        active=[s for s in self.pool if source_dynamic_action_verified(
            s,self.evidence)]
        a,b=deepcopy(active[:2])
        a["key"]="clip_0"
        b["key"]="clip_1"
        ep={"footage":[a,b]}
        with patch.dict(os.environ,{
                "GUSTAVA_SOURCE_ACTION_EVIDENCE_REQUIRED":"1"}):
            self.assertEqual(len(require_native_sources(ep)),2)
            bad=deepcopy(ep)
            bad["footage"][1]["native_4k_sha256"]="0"*64
            with self.assertRaises(ValueError):
                require_native_sources(bad)


if __name__=="__main__":
    unittest.main()
