"""Fully offline narration-completeness tests."""
import unittest
import voice_qa as q


class VoiceQATests(unittest.TestCase):
    def test_normalization_preserves_short_words(self):
        self.assertEqual(q.tokens("Ёж в шлёме, а я?"), ["еж", "в", "шлеме", "а", "я"])

    def test_perfect_readback(self):
        s = "Вот проверка шлема и колеса, а теперь идём домой после поездки."
        result = q.score(s, s)
        self.assertTrue(result["passed"])
        self.assertEqual(result["lexical_coverage"], 1.0)

    def test_swallowed_tail_is_blocked(self):
        s = "Перед поездкой проверь колёса, тормоза и свет. Затем выбирай безопасный маршрут домой."
        t = "Перед поездкой проверь колёса тормоза и свет. Затем выбирай безопасный"
        self.assertFalse(q.score(s, t)["passed"])

    def test_short_words_dropped_is_blocked(self):
        s = "Я и ты поехали в город, а он остался дома на своём старом мотоцикле."
        t = "ты поехали город он остался дома своём старом мотоцикле"
        self.assertFalse(q.score(s, t)["passed"])

    def test_extra_words_not_accepted_as_full_readback(self):
        self.assertFalse(q.score("Сначала проверь двигатель, затем шлем, потом дорогу.",
                                 "Проверь двигатель.")["passed"])


if __name__ == "__main__":
    unittest.main()
