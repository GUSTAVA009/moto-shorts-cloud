"""Actual MP4: never caption engine work while road shot still fills frame."""
import copy
import json
from pathlib import Path
import unittest

import preview_queue as pq
import render_episode as r
from moto_assets import source_id
from editorial_guard import validate_catalog

EP_ID="moto-city-3a2aad34e115"
OLD_FP="730b9c9054aacca1f6d789d7704e9d655292e49cdef68a2d8a36ad20fc374faa"
OLD_MP4="d4773cab50f7eb67c8ab598b712fa70cac2b03bcf58ff677c3cdfac86a9362a7"
VOICE_REF="ed27b23b9f86345c45263ab28957e96fd2d399379b3ea90ed9fbc75be183a3cc"

class ActionCutCaptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=json.loads((Path(__file__).parent/"episodes.json").read_text("utf8"))
        cls.ep=next(x for x in cls.catalog["episodes"] if x["id"]==EP_ID)
    def setUp(self):
        self.ep=copy.deepcopy(self.__class__.ep)
        self.receipt={
            "id":EP_ID,"state":"preview_ready",
            "attempt_count":2,"run_id":"41374584510",
            "preview_fingerprint":OLD_FP,"voice_qa_passed":True,
            "mixed_audio_qa_passed":True,
            "voice_profile":"gustava_original_qwen3_v1",
            "selfhosted_reference_sha256":VOICE_REF,
        }
        self.fp=pq.preview_fingerprint(self.ep)
    def test_real_engine_action_caption_starts_after_true_video_cut(self):
        plan=[{"source":"clip_0","start":0,"seconds":6.545},
              {"source":"clip_1","start":0,"seconds":6.545}]
        caption=r.caption_schedule(self.ep,12.967,plan)
        opening=caption[0]
        middle=caption[1]
        ending=caption[2]
        self.assertEqual(middle[0],"caption_middle")
        real_cut=plan[0]["seconds"]-self.ep["opening_trim_seconds"]
        self.assertAlmostEqual(real_cut,6.445)
        self.assertGreater(middle[1],real_cut)
        self.assertLessEqual(middle[1]-real_cut,0.15)
        self.assertLess(middle[2],ending[1])
        self.assertGreater(middle[1],opening[2])
        self.assertTrue(self.ep["align_middle_caption_to_second_scene"])
        self.assertEqual(self.ep["visual_revision_evidence"]["prior_mp4_sha256"], OLD_MP4)
        self.assertEqual([source_id(x) for x in self.ep["footage"]],["35963831","mixkit-41937"])
        self.assertFalse(self.ep["auto_publish"])
        validate_catalog(self.catalog)
    def test_one_private_sha_bound_retry_not_public_reupload(self):
        self.assertTrue(pq.eligible_retry(self.ep,self.receipt,self.fp))
        self.assertFalse(pq.eligible_retry(self.ep,self.receipt,OLD_FP))
        for k,v in (
            ("run_id","41374584511"),("attempt_count",3),
            ("preview_fingerprint","b"*64),("voice_qa_passed",False),
            ("mixed_audio_qa_passed",False),
            ("voice_profile","other"),("selfhosted_reference_sha256","c"*64),
        ):
            rec=dict(self.receipt,**{k:v})
            self.assertFalse(pq.eligible_retry(self.ep,rec,self.fp),k)
        for k in ("prior_mp4_sha256","prior_run_id","prior_preview_fingerprint",
                  "old_caption_start_seconds","old_second_scene_start_seconds",
                  "old_second_scene_start_source_duration_seconds",
                  "opening_trim_seconds","old_caption_early_by_seconds",
                  "source_ids","source_licenses_unchanged","max_total_attempts",
                  "previous_voice_qa_passed","previous_final_mix_qa_passed",
                  "never_publish_on_visual_retry"):
            altered=copy.deepcopy(self.ep)
            altered["visual_revision_evidence"][k]="wrong"
            self.assertFalse(pq.eligible_retry(altered,self.receipt,self.fp),k)
        for k,v in (("auto_publish",True),
                    ("voice_engine","unapproved"),
                    ("voice_profile","unapproved"),
                    ("selfhosted_voice_id","unapproved"),
                    ("align_middle_caption_to_second_scene",False)):
            altered=copy.deepcopy(self.ep)
            altered[k]=v
            self.assertFalse(pq.eligible_retry(altered,self.receipt,self.fp),k)
        altered=copy.deepcopy(self.ep)
        altered["footage"][0]["source_page"]="https://www.pexels.com/video/other-city-10123456/"
        self.assertFalse(pq.eligible_retry(altered,self.receipt,self.fp))

if __name__=="__main__":
    unittest.main()
