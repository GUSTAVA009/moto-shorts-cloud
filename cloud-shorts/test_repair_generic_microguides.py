"""Offline tests: automated micro-guide repair never publishes or changes submitted material."""
import copy
import json
from pathlib import Path
import unittest
from repair_generic_microguides import TREATMENTS, propose, repair_catalog
from editorial_novelty import is_repeated_visual_formula

ROOT=Path(__file__).resolve().parent
CATALOG=json.loads((ROOT/"episodes.json").read_text(encoding="utf8"))


class AutoMicroguideTests(unittest.TestCase):
    def test_review_3_unpublished_originals_without_repetitive_scenic_ab(self):
        result,ids=repair_catalog(CATALOG,max_changes=3)
        # The live catalog evolves: a successful unattended repair may leave
        # no eligible drafts. Exhaustion is valid and must be idempotent.
        self.assertLessEqual(len(ids),3)
        if not ids:
            self.assertEqual(result,CATALOG)
        for ep in result["episodes"]:
            if ep["id"] in ids:
                self.assertEqual(ep["editorial_format"],"original_action_microguide_v1")
                self.assertTrue(ep["auto_preview"])
                self.assertFalse(ep["auto_publish"])
                self.assertTrue(125<=len(ep["narration"])<=160)
                self.assertFalse(is_repeated_visual_formula(ep,result["episodes"]))
                self.assertTrue(ep["creative_treatment"].startswith("microguide_"))
                self.assertEqual(len(ep["footage"]),2)

    def test_published_or_rendered_draft_cannot_be_changed(self):
        result,ids=repair_catalog(CATALOG,max_changes=30)
        for e in CATALOG["episodes"]:
            if e.get("auto_publish") is True:
                n=next(z for z in result["episodes"] if z["id"]==e["id"])
                self.assertEqual(e,n)
        self.assertFalse(any(e["id"] in ids and e.get("auto_publish") is True
                             for e in CATALOG["episodes"]))
        if ids:
            result2,ids2=repair_catalog(CATALOG,excluded_ids=ids,max_changes=30)
            self.assertTrue(all(a not in ids2 for a in ids))
            for e in CATALOG["episodes"]:
                if e["id"] in ids:
                    self.assertEqual(
                        e,next(z for z in result2["episodes"] if z["id"]==e["id"]))

    def test_treatments_are_once_only_even_with_identical_source_pair_type(self):
        altered,ids=repair_catalog(CATALOG,max_changes=99)
        t=[ep["creative_treatment"] for ep in altered["episodes"]
           if ep.get("editorial_format")=="original_action_microguide_v1"
           and str(ep.get("creative_treatment") or "").startswith("microguide_")]
        self.assertEqual(len(t),len(set(t)))
        another,ids2=repair_catalog(altered,max_changes=99)
        self.assertEqual(ids2,[])
        self.assertEqual(altered,another)

    def test_no_voice_substitution(self):
        altered,ids=repair_catalog(CATALOG,max_changes=20)
        before={e["id"]:e for e in CATALOG["episodes"]}
        for e in altered["episodes"]:
            if e["id"] in ids:
                old=before[e["id"]]
                self.assertEqual(e["voice_engine"],old["voice_engine"])
                self.assertEqual(e["voice_profile"],old["voice_profile"])
                self.assertEqual(e["selfhosted_voice_id"],old["selfhosted_voice_id"])
                self.assertEqual(e["footage"],old["footage"])
                self.assertEqual(e["shots"],old["shots"])

    def test_malformed_or_unrelated_or_previous_publication_not_rewritten(self):
        ep=copy.deepcopy(CATALOG["episodes"][-1])
        ep["auto_publish"]=True
        self.assertIsNone(propose(ep,set()))
        ep["auto_publish"]=False
        ep["voice_engine"]="unapproved"
        self.assertIsNone(propose(ep,set()))


if __name__=="__main__":
    unittest.main()
