"""Exactly three individually granted Mixkit Free assets, NEVER a scraper."""
import unittest
import json
from copy import deepcopy
from moto_assets import source_id,validated_media,verified_mixkit
from moto_autocreate import ROOT,curated_mixkit_results
from source_story import scene_for, select_pair

class MixkitWhitelistedSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pool=json.loads((ROOT / "verified_mixkit_pool.json").read_text(encoding="utf8"))
        cls.sources=cls.pool["sources"]
        cls.by_id={source_id(item):item for item in cls.sources}

    def test_only_three_separately_verified_non_mass_licences(self):
        self.assertEqual(self.pool["mode"],"fixed_individual_free_assets")
        self.assertEqual(set(self.by_id),{"mixkit-41936","mixkit-41937","mixkit-43102"})
        for sid,item in self.by_id.items():
            self.assertEqual(validated_media(item),sid)
            self.assertEqual(item["license"],"Mixkit Stock Video Free License")
            self.assertIn("mixkit.co/license/modal/videoFree/",item["license_source_url"])
            self.assertTrue(item["source_page"].startswith("https://mixkit.co/free-stock-video/"))
            self.assertNotIn("mp4_artifact",item)

    def test_no_pretend_license_or_cdn_mismatch(self):
        item=self.by_id["mixkit-41936"]
        for field,value in (("license","Mixkit Stock Video Restricted License"),
                            ("url","https://example.com/41936.mp4"),
                            ("license_source_url","https://fake.example/free")):
            with self.subTest(field=field),self.assertRaises(ValueError):
                validated_media(dict(item,**{field:value}))
        page="<a href='/license/modal/videoFree/'>Mixkit Stock Video Free License</a> https://assets.mixkit.co/videos/41936/41936-720.mp4"
        self.assertEqual(verified_mixkit(item,fetch=lambda url:page),"mixkit-41936")
        with self.assertRaises(ValueError):
            verified_mixkit(item,fetch=lambda url:"Restricted License")

    def test_only_research_verified_actions_and_unchanged_source_pool(self):
        self.assertEqual(scene_for(self.by_id["mixkit-41936"])[0],"oil_change")
        self.assertEqual(scene_for(self.by_id["mixkit-41937"])[0],"oil_change")
        self.assertEqual(scene_for(self.by_id["mixkit-43102"])[0],"approach")
        self.assertEqual({source_id(x) for x in curated_mixkit_results(("repair",),set())},
                         {"mixkit-41936","mixkit-41937"})
        self.assertEqual(curated_mixkit_results(("repair",),{"mixkit-41936","mixkit-41937"}),[])
        # Mixkit appears as licensor, not a fabricated individual creator;
        # do not pair two clips from one stock contributor.
        self.assertEqual(select_pair(self.sources,set()),[])

    def test_unknown_sites_rejected_without_implicit_rights(self):
        good=self.by_id["mixkit-41936"]
        with self.assertRaises(ValueError):
            source_id(dict(good,source_page="https://coub.com/view/41936"))
        with self.assertRaises(ValueError):
            validated_media(dict(good,url="https://assets.mixkit.co/videos/41937/41937-720.mp4"))
        with self.assertRaises(ValueError):
            validated_media(dict(good,source_page="https://mixkit.co/free-stock-video/other-41937/"))

if __name__=="__main__":
    unittest.main()
