import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import render_documentary as rd

class DocumentaryChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg=json.loads((Path(__file__).resolve().parent/"01-rain-production.json").read_text(encoding="utf8"))

    def test_original_script_and_licensed_sources(self):
        result=rd.validate(self.cfg)
        self.assertEqual(result["scenes"],30)
        self.assertEqual(result["new_clips"],16)
        self.assertGreater(result["words_characters"],6500)
        self.assertGreaterEqual(result["own_infographic_scenes"],5)

    def test_reject_prior_shorts_source(self):
        cfg=copy.deepcopy(self.cfg)
        cfg["sources"][0]["id"]="5803637"
        cfg["sources"][0]["url"]="https://www.pexels.com/download/video/5803637/"
        cfg["sources"][0]["source_page"]="https://www.pexels.com/video/published-motorcycle-5803637/"
        with self.assertRaisesRegex(ValueError,"previously used"):
            rd.validate(cfg)

    def test_reject_duplicate_rights(self):
        cfg=copy.deepcopy(self.cfg)
        cfg["sources"][1]=copy.deepcopy(cfg["sources"][0])
        with self.assertRaises(ValueError):
            rd.validate(cfg)

    def test_reject_source_links_in_public_description(self):
        cfg=copy.deepcopy(self.cfg)
        cfg["description"]+="\nhttps://www.pexels.com/video/123"
        with self.assertRaises(ValueError):
            rd.validate(cfg)

    def test_reject_unknown_source_in_a_scene(self):
        cfg=copy.deepcopy(self.cfg)
        cfg["segments"][-1]["visual"]="unknown-video"
        with self.assertRaisesRegex(ValueError,"Unknown source"):
            rd.validate(cfg)

    def test_reject_insufficient_narration(self):
        cfg=copy.deepcopy(self.cfg)
        cfg["segments"]=cfg["segments"][:4]
        with self.assertRaisesRegex(ValueError,"substantial"):
            rd.validate(cfg)

if __name__=="__main__":
    unittest.main()
