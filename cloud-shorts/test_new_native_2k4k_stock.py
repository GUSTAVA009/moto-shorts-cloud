"""Verified seven new, licensed real native 2K/4K sources; never count MP4 drafts."""
import json
from pathlib import Path
import unittest
from native_source_preflight import source_proof
from source_action_evidence import load_evidence, source_dynamic_action_verified
from moto_assets import source_id

ROOT=Path(__file__).resolve().parent

class RealNativeSupply(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items={source_id(s):s for s in json.loads(
            (ROOT/"verified_pexels_pool.json").read_text(encoding="utf8"))["sources"]}
        cls.evidence=load_evidence()

    def test_new_seven_have_exact_signed_source_pixels_and_sha(self):
        ids={"5803627","5198953","5198992","5199342",
             "5199341","40310204","5199365"}
        for sid in ids:
            with self.subTest(source=sid):
                s=self.items[sid]
                proof=source_proof(dict(s,key="clip_0"),"2k")
                self.assertIn(proof["width"],(1440,2160))
                self.assertGreaterEqual(proof["height"],2560)
                self.assertEqual(proof["sha256"],self.evidence[sid]["sha256"])
                self.assertEqual(proof["width"],self.evidence[sid]["width"])
                self.assertEqual(proof["height"],self.evidence[sid]["height"])
                self.assertEqual(self.evidence[sid]["model"],"qwen3.5:4b")
                self.assertEqual(len(self.evidence[sid]["frame_sha256"]),3)

    def test_visual_action_types_not_mislabeled_as_ready_riding(self):
        for sid in ("5803627","5198992"):
            self.assertTrue(source_dynamic_action_verified(
                self.items[sid],self.evidence))
            self.assertEqual(self.evidence[sid]["action"],"riding")
        for sid in ("5199341","5199342","40310204","5199365","5198953"):
            self.assertFalse(source_dynamic_action_verified(
                self.items[sid],self.evidence))
            self.assertNotIn(self.evidence[sid]["action"],("riding","stunt_jump"))

    def test_cannot_rewrite_stock_proof_to_high_resolution(self):
        item=dict(self.items["40310204"])
        item["native_2k_height"]=900
        with self.assertRaisesRegex(ValueError,"PIXELS_NOT_PROVEN"):
            source_proof(dict(item,key="clip_0"),"2k")


if __name__=="__main__":
    unittest.main()
