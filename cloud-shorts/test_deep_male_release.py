"""Deep-male narrator proof is mandatory even if Russian ASR is perfect."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import voice_qa
from test_voice_style import generate_synthetic_voice
from voice_style import apply as apply_deep_male, PROFILE_ID


class AuditedDeepMaleNarratorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.wav = Path(self.tmp.name) / "new_narration.wav"
        generate_synthetic_voice(self.wav)
        self.episode = {
            "id": "verified-motorcycle-episode",
            "voice_engine": "kokoro_ru_dima",
            "narration": "Мотоцикл мчится по дороге. Впереди новый поворот. Какой маршрут нравится тебе?",
        }

    def tearDown(self):
        self.tmp.cleanup()

    @patch("asr_fallback.transcribe")
    def test_old_bright_voice_must_fail_even_with_perfect_words(self, transcribe):
        transcribe.return_value = (self.episode["narration"], "mock-independent-ASR")
        result = voice_qa.check(self.episode, self.wav)
        self.assertFalse(result["passed"])
        self.assertFalse(result["male_voice_verified"])
        self.assertIn("DEEP_MALE_PROFILE", result["reason"])

    @patch("asr_fallback.transcribe")
    def test_verified_lower_male_voice_can_pass_ASR(self, transcribe):
        import shutil
        if not shutil.which("ffmpeg"):
            self.skipTest("FFmpeg needed for real voice-profile transformation")
        transcribe.return_value = (self.episode["narration"], "mock-independent-ASR")
        apply_deep_male(self.wav)
        result = voice_qa.check(self.episode, self.wav)
        self.assertTrue(result["passed"])
        self.assertTrue(result["male_voice_verified"])
        self.assertEqual(result["voice_profile"], PROFILE_ID)
        self.assertEqual(result["voice_profile_pitch"], .86)

        self.wav.with_suffix(".profile.json").unlink()
        result = voice_qa.check(self.episode, self.wav)
        self.assertFalse(result["passed"])
        self.assertFalse(result["male_voice_verified"])


if __name__ == "__main__":
    unittest.main()
