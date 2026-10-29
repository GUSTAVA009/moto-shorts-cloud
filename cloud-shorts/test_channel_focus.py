"""Off-topic Shorts must never enter the GUSTAVA Enduro video factory."""
import copy
import json
from pathlib import Path
import unittest

from channel_focus import assert_motorcycle_episode, is_motorcycle_episode
from editorial_guard import validate_catalog


class ChannelFocusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(
            (Path(__file__).resolve().parent / "episodes.json").read_text("utf8")
        )

    def test_active_queue_is_entirely_motorcycle_related(self):
        active = [e for e in self.catalog["episodes"]
                  if e.get("auto_preview") is True or e.get("auto_publish") is True]
        self.assertGreaterEqual(len(active), 5)
        for ep in active:
            with self.subTest(id=ep["id"]):
                self.assertTrue(is_motorcycle_episode(ep))
        validate_catalog(self.catalog)

    def test_unrelated_video_is_archived_and_denied(self):
        unrelated = {"aviation-round-windows-18", "octopus-camouflage-19",
                     "hydraulic-press-explained-20", "lightning-strikes-again-21",
                     "why-ice-floats-22"}
        for ep in self.catalog["episodes"]:
            if ep["id"] in unrelated:
                with self.subTest(id=ep["id"]):
                    self.assertFalse(ep.get("auto_preview"))
                    self.assertFalse(ep.get("auto_publish"))
                    self.assertFalse(is_motorcycle_episode(ep))
                    with self.assertRaisesRegex(ValueError, "CHANNEL_TOPIC_BLOCKED"):
                        assert_motorcycle_episode(ep)

    def test_renabling_unrelated_script_causes_catalog_rejection(self):
        data = copy.deepcopy(self.catalog)
        bad = next(e for e in data["episodes"] if e["id"] == "why-ice-floats-22")
        bad["auto_preview"] = True
        bad["auto_publish"] = True
        with self.assertRaisesRegex(ValueError, "CHANNEL_TOPIC_BLOCKED"):
            validate_catalog(data)

    def test_unrelated_story_cannot_bypass_by_using_moto_profile(self):
        bad = {"title": "Почему лёд плавает?",
               "narration": "Когда вода замерзает, её плотность снижается.",
               "research_pillar": "motorcycle",
               "channel_niche": "motorcycle",
               "editorial": {"subject": "offroad-motorcycle"}}
        self.assertFalse(is_motorcycle_episode(bad))

    def test_valid_new_enduro_short_is_allowed(self):
        ep = {"title": "Подъём на мотоцикле в грязь",
              "narration": "Райдер преодолевает сложный грунтовый участок.",
              "research_pillar": "motorcycle", "channel_niche": "motorcycle",
              "editorial": {"subject": "enduro-dirtbike-riding"}}
        self.assertTrue(is_motorcycle_episode(ep))

    def test_other_niche_declared_explicitly_is_denied(self):
        ep = {"title": "Мотоцикл у озера",
              "narration": "Мотоцикл в кадре, но тема не о нём.",
              "channel_niche": "science",
              "editorial": {"bike": "offroad-trail-motorcycle"}}
        self.assertFalse(is_motorcycle_episode(ep))


if __name__ == "__main__":
    unittest.main()
