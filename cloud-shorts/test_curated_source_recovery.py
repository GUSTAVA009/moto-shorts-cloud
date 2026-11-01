"""Repro: free curated footage must offer meaningful, different action pairs.

No network calls or copyrighted assets in tests. Pexels metadata is an
editorial *candidate*: final footage bytes, live rights and frames are still
validated at render. Candidates do not count as finished MP4s.
"""
import json
from pathlib import Path
import unittest
from moto_assets import validated_media,source_id
from moto_autocreate import ROOT
from source_story import select_pair, scene_for, compose, require_filmable

POOL = ROOT / "verified_pexels_pool.json"


class CuratedRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pool=json.loads(POOL.read_text("utf8"))["sources"]

    def test_all_stock_ids_unique_with_https_and_documented_creator(self):
        ids=[]
        for source in self.pool:
            ids.append(validated_media(source))
            self.assertGreaterEqual(len(source["author"].strip()),3)
            self.assertEqual(source["license"],"Pexels License")
        self.assertEqual(len(ids),len(set(ids)))

    def test_new_race_and_muddy_track_give_two_different_actions(self):
        race=next(x for x in self.pool if source_id(x)=="32034080")
        mud=next(x for x in self.pool if source_id(x)=="36365086")
        self.assertNotEqual(race["author"].casefold(),mud["author"].casefold())
        self.assertEqual({scene_for(race)[0],scene_for(mud)[0]},{"race","mud"})
        pair=select_pair([race,mud],set())
        self.assertEqual(len(pair),2)
        story=compose(pair,[])
        self.assertEqual(len(require_filmable(story,pair)),2)
        self.assertLessEqual(len(story["title"]),100)
        self.assertNotIn("https://",story["description"])

    def test_recognized_sources_cannot_be_reused(self):
        race=next(x for x in self.pool if source_id(x)=="32034080")
        mud=next(x for x in self.pool if source_id(x)=="36365086")
        self.assertEqual(select_pair([race,mud],{source_id(race)}),[])
        self.assertEqual(select_pair([race,mud],{source_id(mud)}),[])

    def test_metadata_is_not_a_completed_video(self):
        from pathlib import Path
        pool=json.loads(POOL.read_text("utf8"))
        self.assertNotIn("mp4_artifact",pool)
        for source in pool["sources"]:
            self.assertNotIn("reviewed_mp4_sha256",source)


if __name__=="__main__":
    unittest.main()
