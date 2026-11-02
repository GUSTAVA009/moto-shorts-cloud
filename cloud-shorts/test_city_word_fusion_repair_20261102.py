"""Real original Qwen raw ASR word-fusion: one private evidence-bound reword retry."""
import copy
import json
from pathlib import Path
import unittest
import preview_queue as pq
from editorial_guard import validate_catalog
from render_episode import validate_episode
from moto_assets import source_id

EP="moto-city-3a2aad34e115"
ORIGINAL="Мотоцикл в двух сценах: байкер едет по городской улице. На другом видео механик меняет масло в мотоцикле. Это независимые съёмки. Что ближе тебе?"
FIXED="Мотоцикл в двух сценах: байкер едет по городской улице. Вторая сцена: механик меняет масло в мотоцикле. Это независимые съёмки. Что ближе тебе?"
SHA="cf3c18ae89f5d1dd8b37b009ea923dffae542bb40a2ff16dfaef162b50a5691c"
FP="8ea4ff16627b5ef49c0a154f490d70214c351400986aabfb715c603e4cd43811"
REF="ed27b23b9f86345c45263ab28957e96fd2d399379b3ea90ed9fbc75be183a3cc"

class PrivateWordFusionRetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=json.loads((Path(__file__).parent/"episodes.json").read_text("utf8"))
        cls.episode=next(x for x in cls.catalog["episodes"] if x["id"]==EP)
    def setUp(self):
        self.ep=copy.deepcopy(self.episode)
        self.receipt={
          "id":EP,"state":"preview_ready","run_id":"41373650226",
          "attempt_count":1,"preview_fingerprint":FP,
          "voice_qa_passed":False,"mixed_audio_qa_passed":False,
          "voice_profile":"gustava_original_qwen3_v1",
          "selfhosted_reference_sha256":REF,
        }
        self.fp=pq.preview_fingerprint(self.ep)
    def test_real_mixed_and_raw_word_fusion_is_reworded_not_asr_whitelisted(self):
        self.assertEqual(self.ep["narration"],FIXED)
        self.assertFalse("видеомеханик" in FIXED.casefold())
        self.assertFalse("На другом видео механик" in FIXED)
        self.assertEqual(self.ep["voice_revision_evidence"]["prior_original_narration"],ORIGINAL)
        self.assertEqual(self.ep["voice_revision_evidence"]["prior_mp4_sha256"],SHA)
        self.assertEqual([source_id(x) for x in self.ep["footage"]],["35963831","mixkit-41937"])
        self.assertIs(self.ep["auto_publish"],False)
        validate_episode(self.ep)
        validate_catalog(self.catalog)
        self.assertNotEqual(FP,self.fp)
        self.assertTrue(pq.eligible_retry(self.ep,self.receipt,self.fp))
    def test_no_unproved_retry_or_voice_swap_or_public_release(self):
        self.assertFalse(pq.eligible_retry(self.ep,self.receipt,FP))
        for key,val in (
            ("run_id","41373650227"),("attempt_count",2),
            ("preview_fingerprint","b"*64),
            ("voice_qa_passed",True),("mixed_audio_qa_passed",True),
            ("voice_profile","wrong"),("selfhosted_reference_sha256","c"*64),
        ):
            altered=dict(self.receipt,**{key:val})
            self.assertFalse(pq.eligible_retry(self.ep,altered,self.fp),key)
        for field in ("prior_run_id","prior_mp4_sha256","prior_preview_fingerprint",
                      "raw_coverage","mixed_coverage","expected_phrase",
                      "recognized_phrase","immutable_source_ids",
                      "independent_voice_reference_sha256","editorial_remains_private",
                      "max_total_preview_attempts"):
            changed=copy.deepcopy(self.ep)
            changed["voice_revision_evidence"][field]="invalid"
            self.assertFalse(pq.eligible_retry(changed,self.receipt,self.fp),field)
        for field,value in (("voice_engine","unapproved"),
                            ("voice_profile","unapproved"),
                            ("selfhosted_voice_id","unapproved"),
                            ("auto_publish",True),("narration",ORIGINAL)):
            changed=copy.deepcopy(self.ep)
            changed[field]=value
            self.assertFalse(pq.eligible_retry(changed,self.receipt,self.fp),field)
        changed=copy.deepcopy(self.ep)
        changed["footage"][0]["source_page"]="https://www.pexels.com/video/other-12345678/"
        self.assertFalse(pq.eligible_retry(changed,self.receipt,self.fp))
    def test_no_relaxed_speech_quality_threshold(self):
        from qa_autorepair import MIN_COVERAGE
        self.assertGreaterEqual(MIN_COVERAGE,0.97)
        self.assertEqual(len([e for e in self.catalog["episodes"] if e["id"]==EP]),1)

if __name__=="__main__":
    unittest.main()
