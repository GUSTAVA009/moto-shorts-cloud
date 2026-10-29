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

    def test_generative_script_requires_real_model_credentials(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {"OPENAI_API_KEY": "", "OPENROUTER_API_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "MODEL_MISSING"):
                s.original_story(s.THEMES[0], [], [])

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
