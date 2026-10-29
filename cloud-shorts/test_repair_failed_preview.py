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

    def test_bounded_phonetic_rewrite_preserves_meaning(self):
        new = r.simple_rewrite("Райдер на мотоцикле едет в лесу.",
                               "Райдер но мотоцикли едет в лесу.")
        self.assertEqual(new, "Райдер на своём байке едет в лесу.")

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
        new = r.repair_episode(c, self.ep_id, raw, mixed, receipt)
        self.assertIsNotNone(new)
        ep = next(e for e in new["episodes"] if e["id"] == self.ep_id)
        self.assertIn("на своём байке", ep["narration"])
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
