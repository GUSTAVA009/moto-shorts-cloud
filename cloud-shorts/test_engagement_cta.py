"""No-network tests for voluntary and safe audience-building CTA copy."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from engagement_cta import validate_cta, build_description, overlay_filters, validate_cta_mix


class GrowthCTATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.episodes = json.loads(
            (Path(__file__).parent / "episodes.json").read_text(encoding="utf8")
        )["episodes"]

    def test_every_episode_has_a_varied_natural_cta(self):
        result = validate_cta_mix(self.episodes)
        self.assertTrue(all(result[k] >= 1 for k in ("subscribe","comment","like","share")))
        self.assertEqual(sum(result.values()),len(self.episodes))

    def test_no_links_in_public_description_and_one_call_to_action(self):
        for ep in self.episodes:
            with self.subTest(ep=ep["id"]):
                text = build_description(ep)
                self.assertNotIn("https:",text)
                self.assertNotIn("pexels.com",text)
                self.assertEqual(text.count(ep["cta"]["description"]), 1)
                self.assertTrue(text.rstrip().endswith("#shorts"))

    def test_cta_video_overlay_starts_near_end_and_not_on_youtube_bottom_controls(self):
        with tempfile.TemporaryDirectory() as work:
            ep = self.episodes[-1]
            filters = overlay_filters(ep,work,9.0,"/font.ttf")
            self.assertEqual(len(filters),2)
            self.assertTrue((Path(work)/"engagement_lower_third.txt").exists())
            self.assertIn("y=950",filters[0])
            self.assertIn("7.100,8.830",filters[0])
            self.assertIn("fontsize=27",filters[1])

    def test_no_incentivized_or_deceptive_requests(self):
        ep=copy.deepcopy(self.episodes[-1])
        ep["cta"]["description"]="Подписка за подписку, обещаю тебе миллион!"
        with self.assertRaises(ValueError):
            validate_cta(ep)
        ep=copy.deepcopy(self.episodes[-1])
        ep["cta"]["description"]="Посмотри https://somesite.com."
        with self.assertRaises(ValueError):
            validate_cta(ep)

    def test_not_four_asks_in_every_episode(self):
        for ep in self.episodes:
            self.assertIn(ep["cta"]["kind"],("subscribe","comment","like","share"))
            self.assertLessEqual(len(ep["cta"]["overlay"]),32)


if __name__ == "__main__":
    unittest.main()
