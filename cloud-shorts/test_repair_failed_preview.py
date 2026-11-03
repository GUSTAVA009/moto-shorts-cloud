"""Safe automated unreleased-script repairs without network or model imports."""
import copy
import json
from pathlib import Path
import unittest

import repair_failed_preview as r


class FailedPreviewRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = json.loads((Path(__file__).parent / "episodes.json").read_text(encoding="utf8"))
        cls.base = data
        cls.ep_id = next(e["id"] for e in reversed(data["episodes"])
                         if e.get("auto_publish") and e.get("voice_engine") == "kokoro_ru_dima")

    def reports(self):
        raw = {"episode_id": self.ep_id, "passed": False,
               "recognized_text": "Райдер но мотоцикли уверенно едет в лесу"}
        mixed = {"episode_id": self.ep_id, "passed": False}
        ledger = {"id": self.ep_id, "state": "preview_ready",
                  "attempt_count": 1, "voice_qa_passed": False,
                  "mixed_audio_qa_passed": False}
        return raw, mixed, ledger

    def episode(self):
        c = copy.deepcopy(self.base)
        item = next(e for e in c["episodes"] if e["id"] == self.ep_id)
        item["narration"] = "Райдер на мотоцикле уверенно едет в лесу. " + item["narration"]
        return c

    def test_auto_phonetic_repair_of_real_private_cartoon_b_original_jump(self):
        from preview_queue import preview_fingerprint, eligible_retry
        from selfhosted_voice import CARTOON_B_REFERENCE_SHA, CARTOON_B_PROFILE_ID
        catalog=copy.deepcopy(self.base)
        slug="moto-training-5d7cc0e964be"
        episode=next(x for x in catalog["episodes"] if x["id"]==slug)
        self.assertFalse(episode["auto_publish"])
        self.assertIn("прыгает с трамплина",episode["narration"])
        receipt={"id":slug,"state":"preview_ready","attempt_count":1,
                 "run_id":"41549749487",
                 "preview_fingerprint":preview_fingerprint(episode),
                 "voice_qa_passed":False,"mixed_audio_qa_passed":False,
                 "selfhosted_reference_sha256":CARTOON_B_REFERENCE_SHA}
        raw={"episode_id":slug,"passed":False,
             "recognized_text":episode["narration"].replace("трамплина","тромплина"),
             "lexical_coverage":.957,"voice_profile":CARTOON_B_PROFILE_ID,
             "selfhosted_reference_sha256":CARTOON_B_REFERENCE_SHA,
             "voice_speaker":"gustava-cartoon-b-v1"}
        mixed={"episode_id":slug,"passed":False,"lexical_coverage":.957,
               "source":"FINAL_MIXED_MP4","mp4_sha256":"b"*64}
        result=r.repair_episode(catalog,slug,raw,mixed,receipt)
        self.assertIsNotNone(result)
        updated=next(x for x in result["episodes"] if x["id"]==slug)
        self.assertIn("совершает прыжок",updated["narration"])
        self.assertNotIn("тромплина",updated["narration"])
        self.assertFalse(updated["auto_publish"])
        self.assertTrue(updated["voice_revision_requested"])
        self.assertTrue(eligible_retry(updated,receipt,preview_fingerprint(updated)))
        tampered=copy.deepcopy(updated)
        tampered["voice_revision_evidence"]["prior_mp4_sha256"]="not-real-sha"
        self.assertFalse(eligible_retry(tampered,receipt,preview_fingerprint(tampered)))
        raw["recognized_text"]="другая непонятная речь"
        self.assertIsNone(r.repair_episode(catalog,slug,raw,mixed,receipt))
        raw["recognized_text"]=episode["narration"].replace("трамплина","тромплина")
        receipt["attempt_count"]=2
        self.assertIsNone(r.repair_episode(catalog,slug,raw,mixed,receipt))
        receipt["attempt_count"]=1
        raw["selfhosted_reference_sha256"]="0"*64
        self.assertIsNone(r.repair_episode(catalog,slug,raw,mixed,receipt))

    def test_bounded_phonetic_rewrite_preserves_meaning(self):
        new = r.simple_rewrite("Райдер на мотоцикле едет в лесу.",
                               "Райдер но мотоцикли едет в лесу.")
        self.assertEqual(new, "Райдер на байке едет в лесу.")

    def test_never_copy_fake_asr_word_as_new_script(self):
        self.assertIsNone(r.simple_rewrite("Чистый голос звучит мягко.",
                                           "Чистый голас звучит мягко."))

    def test_no_model_no_forged_rewrite_unknown_phrase(self):
        raw, mixed, receipt = self.reports()
        raw["recognized_text"] = "Мотоцикл едет по лесу"
        c = copy.deepcopy(self.base)
        self.assertIsNone(r.repair_episode(c, self.ep_id, raw, mixed, receipt))

    def test_approved_unpublished_one_sentence_repaired(self):
        raw, mixed, receipt = self.reports()
        c = self.episode()
        source = next(e for e in c["episodes"] if e["id"] == self.ep_id)["narration"]
        raw["recognized_text"] = source.replace("на мотоцикле", "но мотоцикли")
        new = r.repair_episode(c, self.ep_id, raw, mixed, receipt)
        self.assertIsNotNone(new)
        ep = next(e for e in new["episodes"] if e["id"] == self.ep_id)
        self.assertIn("на байке", ep["narration"])
        self.assertTrue(ep["voice_revision_requested"])

    def test_no_repair_of_good_or_unknown_outcome(self):
        raw, mixed, receipt = self.reports()
        c = self.episode()
        receipt["state"] = "reserved"
        self.assertIsNone(r.repair_episode(c, self.ep_id, raw, mixed, receipt))
        receipt["state"] = "preview_ready"
        receipt["attempt_count"] = 3
        self.assertIsNone(r.repair_episode(c, self.ep_id, raw, mixed, receipt))
        receipt["attempt_count"] = 1
        raw["passed"] = True
        mixed["passed"] = True
        self.assertIsNone(r.repair_episode(c, self.ep_id, raw, mixed, receipt))


if __name__ == "__main__":
    unittest.main()
