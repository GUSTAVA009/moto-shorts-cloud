"""Test source replacement only after a confirmed unpublished tech failure."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import source_repair as s
import moto_autocreate as gen


class FailedFootageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((Path(__file__).parent / "episodes.json").read_text("utf8"))
        cls.id = "forest-corner-23"

    def diag(self):
        return {"attempts": [{"status":"technical_error", "source_failure":True}]}

    def receipt(self):
        return {"id":self.id, "state":"reserved", "attempt_count":1}

    def media(self):
        return [
          {"key":"a","url":"https://www.pexels.com/download/video/90000111/",
           "source_page":"https://www.pexels.com/video/motorcycle-forest-90000111/",
           "license":"Pexels License","author":"Movie contributor A","duration":24},
          {"key":"b","url":"https://www.pexels.com/download/video/90000112/",
           "source_page":"https://www.pexels.com/video/motorcycle-woods-90000112/",
           "license":"Pexels License","author":"Movie contributor B","duration":24},
        ]

    def test_recognizes_real_episode_environment(self):
        ep = next(e for e in self.catalog["episodes"] if e["id"] == self.id)
        self.assertEqual(s.episode_theme(ep)[0], "forest")

    def test_recovery_uses_unseen_rights_cleared_sources(self):
        result = s.source_repair(self.catalog, self.id,
                                 self.receipt(), self.diag(), self.media())
        self.assertIsNotNone(result)
        e = next(x for x in result["episodes"] if x["id"] == self.id)
        self.assertEqual(len(e["shots"]), 12)
        self.assertEqual(e["source_revision_reason"], "unavailable_source_replaced")
        self.assertEqual(len({x["source_page"] for x in e["footage"]}), 2)

    def test_no_reuse_even_if_api_returns_published_media(self):
        result = s.source_repair(self.catalog, self.id, self.receipt(), self.diag(),
                                 self.media(), permanently_used={"90000111"})
        self.assertIsNone(result)

    def test_source_discovery_uses_curated_stock_without_pexels_key(self):
        two=self.media()
        with patch.object(s,"curated_pexels_results",return_value=two) as bank, \
             patch.object(s,"commons_results",side_effect=AssertionError("Commons not needed")):
            discovered=s.discover_new_sources(gen.THEMES[0],set(),"")
        self.assertEqual(len(discovered),2)
        bank.assert_called_once()
        self.assertNotEqual(discovered[0]["author"],discovered[1]["author"])

    def test_no_repair_of_other_failure_types_or_unverified_state(self):
        for status in ("preview_ready", "queued", "draft"):
            receipt = dict(self.receipt(), state=status)
            self.assertIsNone(s.source_repair(self.catalog, self.id,
                                              receipt, self.diag(), self.media()))
        receipt = dict(self.receipt(), attempt_count=3)
        self.assertIsNone(s.source_repair(self.catalog, self.id, receipt,
                                          self.diag(), self.media()))
        diag = {"attempts":[{"status":"technical_error", "source_failure":False}]}
        self.assertIsNone(s.source_repair(self.catalog, self.id,
                                          self.receipt(), diag, self.media()))

    def test_no_unlicensed_or_same_author_sources(self):
        same = self.media()
        same[1]["author"] = same[0]["author"]
        self.assertIsNone(s.source_repair(self.catalog, self.id,
                                          self.receipt(), self.diag(), same))


if __name__ == "__main__":
    unittest.main()
