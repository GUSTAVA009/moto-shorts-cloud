"""Regression: Russian Shorts captions fit the safe horizontal frame."""
import unittest
from caption_layout import layout_caption, readable_caption_text, SAFE_WIDTH


class CaptionLayoutTests(unittest.TestCase):
    def test_real_clipped_titles_fit_without_truncation(self):
        titles = [
            "СТАРЫЙ БАЙК И ИНСТРУМЕНТЫ: мотожизнь",
            "КОЛЕСО И МОТОР: две разные работы",
            "ДВА МОТОТРЮКА: шоу или город?",
            "ПОЧЕМУ КОНУСЫ? Мотоуправление в деле",
            "ТОРМОЗ И МАСЛО: что проверяют в гараже?",
        ]
        for title in titles:
            with self.subTest(title=title):
                item = layout_caption(title)
                self.assertLessEqual(item["max_line_width_px"], SAFE_WIDTH)
                self.assertLessEqual(item["line_count"], 2)
                self.assertEqual(" ".join(item["text"].split()), title)

    def test_missing_font_emoji_does_not_render_as_square(self):
        text = readable_caption_text("ПОЧЕМУ КОНУСЫ? 🏍️ ТРЕНИРОВКА 🔧")
        self.assertEqual(text, "ПОЧЕМУ КОНУСЫ? ТРЕНИРОВКА")
        self.assertEqual(layout_caption("МОТОТРЮКИ 🔥")["text"], "МОТОТРЮКИ")

    def test_long_unbreakable_title_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "CAPTION_OVERFLOW"):
            layout_caption("Б" * 200)

    def test_short_title_stays_one_line(self):
        item = layout_caption("ЧТО ВЫБЕРЕШЬ ТЫ?")
        self.assertEqual(item["line_count"], 1)


if __name__ == "__main__":
    unittest.main()
