"""Offline tests of new licensed stock intake and original Russian story creation."""
import copy
import json
from pathlib import Path
import unittest

import moto_autocreate as s


def fixture(id, name):
    return {
        "id": id,
        "url": "https://www.pexels.com/video/motorcycle-ride-" + str(id) + "/",
        "duration": 24, "user": {"name": name},
        "video_files": [{"id": id, "link": "https://videos.pexels.com/media/demo.mp4"}],
    }


def story():
    return {
        "title": "Мотоцикл и новая дорога: на что смотреть? #shorts",
        "narration": ("Мотоцикл открывает совершенно другую дорогу. Один райдер "
                      "выбирает спокойный маршрут, другой любит извилистую тропу. "
                      "Но важнее всего заранее видеть покрытие и помнить об "
                      "окружающих. А какая дорога нравится тебе больше?"),
        "description": "Две самостоятельные мотоистории, новые маршруты и впечатления. #shorts",
        "caption_start": "НОВАЯ ДОРОГА",
        "caption_middle": "ДВЕ РАЗНЫЕ ПОЕЗДКИ",
        "caption_end": "КАКОЙ МАРШРУТ ТВОЙ?",
    }


class NewMotoSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(
            (Path(__file__).resolve().parent / "episodes.json").read_text(encoding="utf8"))

    def test_pexels_official_source_and_two_authors(self):
        data = {"videos": [fixture(90000001, "Alice Rider"),
                           fixture(90000002, "Bob Mechanic"),
                           fixture(90000003, "Bob Mechanic"),
                           fixture(90000004, "Daria Rider")]}
        def fetch(url, headers):
            self.assertIn("api.pexels.com/v1/videos/search", url)
            self.assertEqual(headers["Authorization"], "not-a-real-key")
            return data
        result = s.pexels_results(s.THEMES[0], 1, "not-a-real-key", fetch=fetch)
        self.assertEqual(len(result), 4)
        selected = s.choose_sources(result, set(), n=3)
        self.assertEqual(len(selected), 3)
        self.assertEqual(len({x["author"] for x in selected}), 3)

    def test_non_motorcycle_pexels_video_rejected(self):
        wrong = fixture(90000001, "Alice Rider")
        wrong["url"] = "https://www.pexels.com/video/cute-cat-90000001/"
        data = {"videos": [wrong]}
        self.assertEqual(s.pexels_results(s.THEMES[0], 1, "demo",
                                         fetch=lambda a,b: data), [])

    def test_no_key_no_invented_stock_sources(self):
        self.assertEqual(s.pexels_results(s.THEMES[0], 1, ""), [])
        self.assertEqual(s.choose_sources([], set()), [])

    def test_offline_story_reserve_without_model_credentials(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {"OPENAI_API_KEY": "", "OPENROUTER_API_KEY": ""}):
            a = s.original_story(s.THEMES[0], [], [])
            b = s.original_story(s.THEMES[0], [], [a["title"]])
        self.assertNotEqual(a["title"], b["title"])
        self.assertTrue(125 <= len(a["narration"]) <= 300)
        self.assertTrue(a["narration"].startswith("Мотоцикл"))
        self.assertEqual(a["_generation_source"], "offline_editorial_reserve_v2")

    def test_verified_public_pexels_pool_stays_unique(self):
        bank = json.loads((Path(__file__).resolve().parent / "verified_pexels_pool.json").read_text("utf8"))
        from moto_assets import validated_media, source_id
        sources = bank["sources"]
        self.assertGreaterEqual(len(sources), 20)
        ids = [source_id(x) for x in sources]
        self.assertEqual(len(ids), len(set(ids)))
        for entry in sources:
            self.assertEqual(validated_media(entry), source_id(entry))
        self.assertTrue(s.curated_pexels_results(s.THEMES[0]))
        self.assertFalse(s.curated_pexels_results(s.THEMES[0], set(ids)))

    def test_offline_fallback_when_inference_service_fails(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {"OPENAI_API_KEY": "", "OPENROUTER_API_KEY": ""}):
            result = s.original_story(s.THEMES[0], [], [],
                  client=("https://model.example", "example-token", "test-model"),
                  fetch=lambda *args: (_ for _ in ()).throw(OSError("Provider unavailable")))
        self.assertEqual(result["_generation_source"], "offline_editorial_reserve_v2")

    def test_active_rolling_batch_script_can_be_used_for_new_episode(self):
        from unittest.mock import patch
        import story_reserve
        planned = story_reserve.at(10_000)
        planned["theme"] = "motocross"
        media = s.pexels_results(s.THEMES[1], 1, "demo",
                fetch=lambda a,b: {"videos": [
                    fixture(90000001, "Alice Rider"),
                    fixture(90000002, "Bob Mechanic"),
                    fixture(90000004, "Daria Rider")]})
        relevant = (dict(self.catalog, episodes=self.catalog["episodes"][:-1])
                    if self.catalog["episodes"][-1]["editorial"]["bike"] == s.THEMES[1][3]
                    else self.catalog)
        with patch.dict("os.environ", {"PEXELS_API_KEY": ""}):
            with patch.object(s, "curated_pexels_results", return_value=media), \
                 patch.object(s, "commons_results", return_value=[]):
                ep = s.create_one(relevant,
                                  source_fetch=lambda *args: [],
                                  commons_fetch=lambda *args: [],
                                  prose_factory=lambda *args: (_ for _ in ()).throw(
                                      AssertionError("Active reserve draft should win")),
                                  prepared_scripts=[planned])
        self.assertEqual(ep["story_reserve_id"], planned["_reserve_id"])
        self.assertEqual(ep["narration"], planned["narration"])
        self.assertEqual(ep["title"], planned["title"])

    def test_supplier_never_repeats_last_motorcycle_type(self):
        from unittest.mock import patch
        catalog = dict(self.catalog)
        last = dict(catalog["episodes"][-1])
        last["editorial"] = dict(last["editorial"], bike=s.THEMES[1][3])
        catalog["episodes"] = list(catalog["episodes"][:-1]) + [last]
        planned = s.offline_original_story(s.THEMES[1], [], [])
        planned["theme"] = "motocross"
        media = s.pexels_results(s.THEMES[1], 1, "test",
                fetch=lambda a,b: {"videos":[
                    fixture(90000001, "Alice Rider"),
                    fixture(90000002, "Bob Mechanic")]})
        with patch.dict("os.environ", {"PEXELS_API_KEY": ""}):
            with patch.object(s, "curated_pexels_results",
                 side_effect=lambda theme,used: media if theme[0]=="motocross" else []):
                with self.assertRaisesRegex(RuntimeError, "NO_NEW_LICENSED_MOTO_CLIPS"):
                    s.create_one(catalog, source_fetch=lambda *a: [],
                                 commons_fetch=lambda *a: [],
                                 prepared_scripts=[planned])

    def test_reject_model_fabricating_numbers(self):
        result = story()
        result["narration"] += " Максимальная скорость 230 километров в час."
        fake = {"choices": [{"message": {"content": json.dumps(result, ensure_ascii=False)}}]}
        with self.assertRaisesRegex(ValueError, "numerical"):
            s.original_story(s.THEMES[0], [], [], client=("https://example.com", "key", "test"),
                             fetch=lambda a,b,c: fake)

    def test_build_vetted_unique_episode(self):
        media = s.pexels_results(s.THEMES[0], 1, "demo",
              fetch=lambda a,b: {"videos": [
                  fixture(90000001, "Alice Rider"), fixture(90000002, "Bob Mechanic"),
                  fixture(90000004, "Daria Rider")]})
        theme = s.choose_theme(self.catalog["episodes"])
        ep = s.assemble_episode(self.catalog, theme, media[:3],
                                story(), len(self.catalog["episodes"]))
        self.assertTrue(ep["auto_publish"])
        self.assertEqual(len(ep["shots"]), 12)
        self.assertEqual(len(ep["footage"]), 3)
        self.assertEqual(len(set(x["source_page"] for x in ep["footage"])), 3)
        self.assertTrue(ep["narration"].startswith("Мотоцикл"))


if __name__ == "__main__":
    unittest.main()
