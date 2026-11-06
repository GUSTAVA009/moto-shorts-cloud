"""Proof-based single private ASR correction for the owner Cartoon B factory."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from preview_queue import eligible_abandoned_owner_phonetic_retry

HERE=Path(__file__).resolve().parent


class ReservedPhoneticRecoveryTests(unittest.TestCase):
    def setUp(self):
        catalog=json.loads((HERE/"episodes.json").read_text(encoding="utf8"))
        self.episode=deepcopy(next(x for x in catalog["episodes"]
                    if x["id"]=="moto-vintage-1211a46b1a90"))
        self.receipt={
            "id":self.episode["id"],"state":"reserved","attempt_count":1,
            "run_id":"42265495571",
            "preview_fingerprint":"41ceab71295cd87ef386492dc42948980fde37da104bd4c7ce7e99d6ada8a796",
            "selfhosted_voice_id":"gustava-cartoon-b-v1",
        }

    def attempt(self, ep=None, receipt=None, conclusion="failure"):
        return eligible_abandoned_owner_phonetic_retry(
            ep if ep is not None else self.episode,
            receipt if receipt is not None else self.receipt,
            "9"*64,conclusion)

    def test_only_real_failed_private_episode_is_revoiced(self):
        self.assertTrue(self.attempt())
        self.assertFalse(self.attempt(conclusion="success"))
        self.assertFalse(self.attempt(conclusion="in_progress"))
        for value in ("preview_ready", "published", "lost"):
            self.assertFalse(self.attempt(receipt=dict(self.receipt,state=value)))
        self.assertFalse(self.attempt(receipt=dict(self.receipt,attempt_count=2)))
        self.assertFalse(self.attempt(ep=dict(self.episode,auto_publish=True)))

    def test_no_replacement_if_footage_or_voice_or_asr_proof_changes(self):
        altered=deepcopy(self.episode)
        altered["voice_engine"]="different_voice"
        self.assertFalse(self.attempt(ep=altered))
        altered=deepcopy(self.episode)
        altered["narration"]=altered["narration"].replace("плавно","быстрее")
        self.assertFalse(self.attempt(ep=altered))
        altered=deepcopy(self.episode)
        altered["footage"][0]["original_sha256"]="0"*64
        self.assertFalse(self.attempt(ep=altered))
        for field,value in (("raw_asr_coverage",1.0),
                             ("expected_word","востоке"),
                             ("prior_artifact_id",0),
                             ("public_upload_permitted",True),
                             ("narrator_reference_sha256","f"*64)):
            altered=deepcopy(self.episode)
            altered["voice_revision_evidence"][field]=value
            self.assertFalse(self.attempt(ep=altered))

    def test_unchanged_recording_fingerprint_cannot_rerender(self):
        self.assertFalse(eligible_abandoned_owner_phonetic_retry(
            self.episode,self.receipt,self.receipt["preview_fingerprint"],"failure"))


if __name__=="__main__":
    unittest.main()
