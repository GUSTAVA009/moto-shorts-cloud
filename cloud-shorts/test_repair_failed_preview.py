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
        # The real automatic Qwen review has ALREADY published this episode.
        # Reconstruct a PRIVATE copy of the failed historical source MP4;
        # never modify the actual released catalog entry.
        episode["auto_publish"]=False
        for field in ("visual_revision_status","reviewed_mp4_sha256",
                      "reviewed_artifact_run_id","automated_frame_review"):
            episode.pop(field,None)
        # This is a regression test for the ORIGINAL failure, not the
        # current mutable episode record. The live repair has ALREADY
        # changed the sentence, so restore the initial 2026-11-03
        # failed speech before testing the safe rewrite in isolation.
        episode["narration"]=episode["narration"].replace(
            "совершает прыжок","прыгает с трамплина")
        for field in ("voice_revision_requested","voice_revision_priority",
                      "voice_revision_reason","voice_revision_evidence"):
            episode.pop(field,None)
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

    def test_owner_voice_second_failed_render_can_be_repaired_without_fixed_retry_cap(self):
        from preview_queue import preview_fingerprint, eligible_retry
        from selfhosted_voice import CARTOON_B_PROFILE_ID, CARTOON_B_REFERENCE_SHA
        catalog=copy.deepcopy(self.base)
        slug="moto-training-5d7cc0e964be"
        old=next(x for x in catalog["episodes"] if x["id"]==slug)
        old["auto_publish"]=False
        for field in ("visual_revision_status","reviewed_mp4_sha256",
                      "reviewed_artifact_run_id","automated_frame_review"):
            old.pop(field,None)
        self.assertTrue(old.get("voice_revision_requested"))
        self.assertIn("совершает прыжок",old["narration"])
        receipt={
            "id":slug,"state":"preview_ready","attempt_count":2,
            "run_id":"41551096759",
            "previous_run_id":old["voice_revision_evidence"]["prior_run_id"],
            "preview_fingerprint":preview_fingerprint(old),
            "selfhosted_reference_sha256":CARTOON_B_REFERENCE_SHA,
            "voice_qa_passed":False,"mixed_audio_qa_passed":False}
        raw={"episode_id":slug,"passed":False,
             "recognized_text":old["narration"].replace(
                 "на мотоцикле","на мотоцикли"),
             "lexical_coverage":.957,"voice_profile":CARTOON_B_PROFILE_ID,
             "selfhosted_reference_sha256":CARTOON_B_REFERENCE_SHA,
             "voice_speaker":"gustava-cartoon-b-v1"}
        mixed={"episode_id":slug,"passed":False,
               "lexical_coverage":.957,"source":"FINAL_MIXED_MP4",
               "mp4_sha256":"d"*64}
        candidate=r.repair_episode(catalog,slug,raw,mixed,receipt)
        self.assertIsNotNone(candidate)
        revised=next(x for x in candidate["episodes"] if x["id"]==slug)
        self.assertIn("на байке",revised["narration"])
        self.assertEqual(revised["voice_revision_evidence"]["prior_attempt_count"],2)
        self.assertEqual(len(revised["voice_revision_hash_history"]),3)
        self.assertTrue(eligible_retry(revised,receipt,
                                       preview_fingerprint(revised)))
        # Same failed run cannot be accepted twice merely by rerunning
        # the repair scheduler or bumping an attempt count.
        self.assertIsNone(r.repair_episode(candidate,slug,raw,mixed,receipt))
        invalid=copy.deepcopy(revised)
        invalid["voice_revision_hash_history"].append(
            invalid["voice_revision_hash_history"][-1])
        self.assertFalse(eligible_retry(invalid,receipt,preview_fingerprint(invalid)))
        first=copy.deepcopy(old)
        first["voice_revision_evidence"]["prior_run_id"]="not-previous-run"
        fake_catalog=copy.deepcopy(catalog)
        next(x for x in fake_catalog["episodes"] if x["id"]==slug).update(first)
        self.assertIsNone(r.repair_episode(fake_catalog,slug,raw,mixed,receipt))

    def test_actual_fused_video_raider_raw_only_failure_is_autorepaired(self):
        from preview_queue import preview_fingerprint, eligible_retry
        from selfhosted_voice import CARTOON_B_PROFILE_ID, CARTOON_B_REFERENCE_SHA
        catalog=copy.deepcopy(self.base)
        slug="moto-forest-5a24107fdebf"
        ep=next(x for x in catalog["episodes"] if x["id"]==slug)
        self.assertIn("На другом видео райдер",ep["narration"])
        self.assertFalse(ep["auto_publish"])
        original_fp=preview_fingerprint(ep)
        receipt={"id":slug,"state":"preview_ready","attempt_count":1,
                 "run_id":"41617140798",
                 "preview_fingerprint":original_fp,
                 "voice_qa_passed":False,"mixed_audio_qa_passed":True,
                 "selfhosted_reference_sha256":CARTOON_B_REFERENCE_SHA}
        # Actual production 41617140798: original ASR 90.9%, final MP4
        # ASR 100%. Changing music gain cannot correct the source fusion.
        raw={"episode_id":slug,"passed":False,
             "recognized_text":ep["narration"].replace(
                 "видео райдер","видеорайдер"),
             "lexical_coverage":.909,"voice_profile":CARTOON_B_PROFILE_ID,
             "selfhosted_reference_sha256":CARTOON_B_REFERENCE_SHA,
             "voice_speaker":"gustava-cartoon-b-v1"}
        mixed={"episode_id":slug,"passed":True,"lexical_coverage":1.0,
               "source":"FINAL_MIXED_MP4","mp4_sha256":"a"*64}
        fixed=r.repair_episode(catalog,slug,raw,mixed,receipt)
        self.assertIsNotNone(fixed)
        new=next(x for x in fixed["episodes"] if x["id"]==slug)
        self.assertIn("Во втором кадре райдер",new["narration"])
        self.assertNotIn("видеорайдер",new["narration"])
        self.assertFalse(new["auto_publish"])
        self.assertEqual(new["voice_revision_evidence"]["prior_mixed_qa_passed"],True)
        self.assertTrue(eligible_retry(new,receipt,preview_fingerprint(new)))
        stale=copy.deepcopy(receipt)
        stale["mixed_audio_qa_passed"]=False
        self.assertFalse(eligible_retry(new,stale,preview_fingerprint(new)))
        # Verbatim same previous run and revised script can't be queued again.
        self.assertIsNone(r.repair_episode(fixed,slug,raw,mixed,receipt))
        unrelated=copy.deepcopy(raw)
        unrelated["recognized_text"]="несвязанный текст"
        self.assertIsNone(r.repair_episode(catalog,slug,unrelated,mixed,receipt))
        wrong=copy.deepcopy(raw)
        wrong["selfhosted_reference_sha256"]="f"*64
        self.assertIsNone(r.repair_episode(catalog,slug,wrong,mixed,receipt))

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
