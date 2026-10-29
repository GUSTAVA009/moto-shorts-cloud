"""QA gates for permanent video/staging uniqueness."""
import copy
import json
from pathlib import Path
import unittest

import editorial_guard as g


class EditorialGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(
            (Path(__file__).resolve().parent / "episodes.json").read_text(encoding="utf8")
        )

    def test_current_catalog_has_distinct_footage_and_scenarios(self):
        result = g.validate_catalog(self.data)
        self.assertGreaterEqual(result["episodes"], 7)
        self.assertGreaterEqual(result["new_unique_video_clips"], 15)
        self.assertEqual(result["unique_editorial_concepts"], result["episodes"])

    def test_previously_published_source_never_reused(self):
        data = copy.deepcopy(self.data)
        ep = data["episodes"][-1]
        ep["footage"][0]["source_page"] = "https://www.pexels.com/video/person-riding-a-motocross-5803637/"
        ep["footage"][0]["url"] = "https://www.pexels.com/download/video/5803637/"
        with self.assertRaisesRegex(ValueError, "STOCK_REUSE_FORBIDDEN"):
            g.validate_catalog(data)

    def test_reuse_between_episodes_rejected_even_if_url_changes(self):
        data = copy.deepcopy(self.data)
        old = data["episodes"][0]["footage"][0]
        data["episodes"][-1]["footage"][0]["source_page"] = old["source_page"]
        data["episodes"][-1]["footage"][0]["url"] = old["url"]
        with self.assertRaisesRegex(ValueError, "STOCK_REUSE_FORBIDDEN"):
            g.validate_catalog(data)

    def test_same_environment_rejected(self):
        data = copy.deepcopy(self.data)
        data["episodes"][-1]["editorial"]["environment"] = data["episodes"][-2]["editorial"]["environment"]
        with self.assertRaisesRegex(ValueError, "settings"):
            g.validate_catalog(data)

    def test_same_people_subject_or_story_rejected(self):
        for field in ["subject", "people", "story"]:
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                last = data["episodes"][-1]["editorial"]
                prior = data["episodes"][-2]["editorial"]
                if field == "subject":
                    last["subject"] = g.editorial_subject(prior)
                    last.pop("bike", None)
                else:
                    last[field] = prior[field]
                with self.assertRaises(ValueError):
                    g.validate_catalog(data)

    def test_generic_science_subject_is_accepted(self):
        self.assertEqual(
            g.editorial_subject({"subject": "science-experiment"}),
            "science-experiment"
        )
        with self.assertRaises(ValueError):
            g.editorial_subject({})

    def test_branding_banned_from_public_description(self):
        data = copy.deepcopy(self.data)
        data["episodes"][-1]["description"] += " ХАПЫЧ"
        with self.assertRaisesRegex(ValueError, "Forbidden"):
            g.validate_catalog(data)


if __name__ == "__main__":
    unittest.main()
