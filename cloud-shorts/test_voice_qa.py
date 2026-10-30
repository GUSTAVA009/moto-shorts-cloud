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

    def test_motocross_latin_asr_spelling_is_not_a_swallowed_word(self):
        reference = ("На гоночной трассе всё решают секунды. Мотоцикл едет быстро. "
                     "Эти кадры сняты на разных площадках. Любишь смотреть мотокросс?")
        heard = reference.replace("мотокросс?", "motocross?")
        report = q.score(reference, heard)
        self.assertEqual(q.tokens("мотокросс"), q.tokens("motocross"))
        self.assertTrue(report["passed"])
        self.assertEqual(report["lexical_coverage"], 1.0)
        self.assertTrue(report["final_word_present"])
        self.assertEqual(report["ending_coverage"], 1.0)

    def test_real_missing_motocross_tail_remains_blocked(self):
        reference = ("На гоночной трассе всё решают секунды. Мотоцикл едет быстро. "
                     "Эти кадры сняты на разных площадках. Любишь смотреть мотокросс?")
        without_tail = reference.replace("мотокросс?", "")
        self.assertFalse(q.score(reference, without_tail)["passed"])
        self.assertFalse(q.score(reference, without_tail)["final_word_present"])
        self.assertFalse(q.score(reference, reference.replace("мотокросс", "supercross"))["passed"])

    def test_swallowed_tail_is_blocked(self):
        s = "Перед поездкой проверь колёса, тормоза и свет. Затем выбирай безопасный маршрут домой."
        t = "Перед поездкой проверь колёса тормоза и свет. Затем выбирай безопасный"
        self.assertFalse(q.score(s, t)["passed"])

    def test_short_words_dropped_is_blocked(self):
        s = "Я и ты поехали в город, а он остался дома на своём старом мотоцикле."
        t = "ты поехали город он остался дома своём старом мотоцикле"
        self.assertFalse(q.score(s, t)["passed"])

    def test_russian_age_and_year_equivalence(self):
        self.assertEqual(q.tokens("Осень тысяча девятьсот восемьдесят второго года."),
                         q.tokens("Осень 1982 года."))
        self.assertEqual(q.tokens("В двадцать три года"),
                         q.tokens("В 23 года"))

    def test_decade_does_not_fake_a_wrong_year(self):
        self.assertEqual(q.tokens("В начале восьмидесятых. Я уехал."),
                         q.tokens("В начале 80-х. Я уехал."))
        self.assertNotEqual(q.tokens("В тысяча девятьсот восемьдесят втором."),
                            q.tokens("В 1882."))

    def test_real_swallowed_number_not_hidden_by_normalization(self):
        original = "В двадцать три года она уехала из Лондона в Америку на мотоцикле."
        mangled = "В двадцать года она уехала из Лондона в Америку на мотоцикле."
        self.assertFalse(q.score(original, mangled)["passed"])

    def test_extra_words_not_accepted_as_full_readback(self):
        self.assertFalse(q.score("Сначала проверь двигатель, затем шлем, потом дорогу.",
                                 "Проверь двигатель.")["passed"])


if __name__ == "__main__":
    unittest.main()
