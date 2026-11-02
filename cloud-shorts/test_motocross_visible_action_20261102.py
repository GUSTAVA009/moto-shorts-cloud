"""Bounded repair for an actual, SHA-pinned first-shot visual mismatch."""
import json
from pathlib import Path
import unittest
from copy import deepcopy

import preview_queue as pq
from moto_assets import source_id, validated_media
from render_episode import validate_episode

EPISODE_ID = "moto-motocross-223d9ab5c67d"
PRIOR_MP4 = "1726369965ae387dbb70bbc036c61fcba7fd3dc84de528e3456aac53fb8488e5"
PRIOR_FP = "b371f99d486f19f3b38ab630522ac5677d876f950fc16a106e0d59c9f49a4ba4"

class MotocrossVisibleActionRepairTests(unittest.TestCase):
    def setUp(self):
        catalog = json.loads((Path(__file__).parent / "episodes.json").read_text("utf8"))
        self.ep = deepcopy(next(x for x in catalog["episodes"] if x["id"] == EPISODE_ID))
        self.rec = {
            "id": EPISODE_ID, "state": "preview_ready",
            "run_id": "41370745453", "attempt_count": 1,
            "preview_fingerprint": PRIOR_FP, "voice_qa_passed": True,
            "mixed_audio_qa_passed": True,
        }
        self.new_fp = pq.preview_fingerprint(self.ep)
        self.catalog = catalog

    def test_replacement_is_new_license_verified_and_subject_visible_in_source_review(self):
        self.assertEqual(self.ep["auto_publish"],False)
        self.assertEqual(self.ep["voice_engine"],"gustava_selfhosted_qwen3")
        self.assertEqual([source_id(x) for x in self.ep["footage"]],
                         ["32399067","9607287"])
        self.assertEqual(self.ep["footage"][0]["author"],"Harvey Tan Villarino")
        self.assertEqual(self.ep["visual_revision_evidence"]["prior_mp4_sha256"], PRIOR_MP4)
        self.assertLessEqual(self.ep["shots"][0]["seconds"],
                             self.ep["footage"][0]["duration"]-.2)
        self.assertEqual(validated_media(self.ep["footage"][0]),"32399067")
        validate_episode(self.ep)
        self.assertNotEqual(self.new_fp, PRIOR_FP)

    def test_only_exact_previous_passed_preview_may_be_rerendered_privately(self):
        self.assertTrue(pq.eligible_retry(self.ep,self.rec,self.new_fp))
        self.assertFalse(pq.eligible_retry(self.ep,self.rec,PRIOR_FP))
        for field,value in (("run_id","41370745454"),
                            ("attempt_count",2),("voice_qa_passed",False),
                            ("mixed_audio_qa_passed",False),
                            ("preview_fingerprint","b"*64)):
            invalid = dict(self.rec, **{field:value})
            self.assertFalse(pq.eligible_retry(self.ep,invalid,self.new_fp))

    def test_no_release_or_free_retry_after_proof_or_footage_tamper(self):
        for proof_field in ("prior_mp4_sha256","prior_run_id",
                            "prior_source_id","replacement_source_id",
                            "prior_preview_fingerprint"):
            invalid=deepcopy(self.ep)
            invalid["visual_revision_evidence"][proof_field]="tampered"
            self.assertFalse(pq.eligible_retry(invalid,self.rec,self.new_fp))
        invalid=deepcopy(self.ep)
        invalid["footage"][0]["source_page"]=(
            "https://www.pexels.com/video/another-motorcycle-99999999/")
        self.assertFalse(pq.eligible_retry(invalid,self.rec,self.new_fp))
        approved=deepcopy(self.ep)
        approved["auto_publish"]=True
        self.assertFalse(pq.eligible_retry(approved,self.rec,self.new_fp))
        self.assertEqual(self.ep["auto_publish"],False)


if __name__ == "__main__":
    unittest.main()
