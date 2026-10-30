"""Vendor-independent publication QA tests: no network, no posting."""
import tempfile
from pathlib import Path
import unittest

import publication_safety as p


class PublicationQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.video = Path(self.temp.name) / "moto.mp4"
        self.video.write_bytes(b"M" * 500001)
        self.episode = {
            "id": "motocross-original-23", "auto_publish": True,
            "voice_engine": "kokoro_ru_dima",
            "title": "Мотокросс: крутой подъём",
            "narration": "Райдер на мотоцикле преодолевает препятствия.",
            "editorial": {"bike": "offroad-motorcycle"},
            "footage": [{"license": "Pexels License"}],
        }
        self.meta = {
            "episode_id": self.episode["id"],
            "title": self.episode["title"],
            "description": "Новые мотосцены, оригинальная озвучка.",
        }
        self.qa = {
            "episode_id": self.episode["id"],
            "passed": True, "status": "passed",
            "lexical_coverage": .99, "ending_coverage": .99,
            "final_word_present": True, "male_voice_verified": True,
            "voice_profile": "gustava_male_natural_v4",
            "mixed_audio": {
                "episode_id": self.episode["id"],
                "source": "FINAL_MIXED_MP4", "passed": True,
                "lexical_coverage": .99, "final_word_present": True,
                "numerics_match": True,
                "mp4_sha256": p.file_sha256(self.video),
            },
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_motorcycle_clip(self):
        self.assertTrue(p.publication_allowed(self.episode, self.meta, self.qa, self.video))

    def test_old_voice_profile_never_passes_publication(self):
        self.qa.pop("male_voice_verified")
        with self.assertRaisesRegex(ValueError, "DEEP_MALE_VOICE_REQUIRED"):
            p.publication_allowed(self.episode, self.meta, self.qa, self.video)

    def test_missing_words_blocked(self):
        self.qa["lexical_coverage"] = .60
        with self.assertRaisesRegex(ValueError, "narration"):
            p.publication_allowed(self.episode, self.meta, self.qa, self.video)

    def test_missing_mixed_audio_blocked(self):
        del self.qa["mixed_audio"]
        with self.assertRaisesRegex(ValueError, "mixed Russian"):
            p.publication_allowed(self.episode, self.meta, self.qa, self.video)

    def test_wrong_video_sha_blocked(self):
        self.qa["mixed_audio"]["mp4_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "does not match"):
            p.publication_allowed(self.episode, self.meta, self.qa, self.video)

    def test_off_topic_blocked_even_with_approved_flags(self):
        self.episode["title"] = "Почему лёд плавает?"
        self.episode["narration"] = "Вода изменяет плотность при охлаждении."
        self.episode["editorial"] = {"subject": "ice-science"}
        with self.assertRaisesRegex(ValueError, "CHANNEL_TOPIC_BLOCKED"):
            p.publication_allowed(self.episode, self.meta, self.qa, self.video)

    def test_unlicensed_footage_blocked(self):
        self.episode["footage"][0]["license"] = "Unknown"
        with self.assertRaisesRegex(ValueError, "rights"):
            p.publication_allowed(self.episode, self.meta, self.qa, self.video)

    def test_unapproved_video_blocked(self):
        self.episode["auto_publish"] = False
        with self.assertRaisesRegex(ValueError, "explicitly"):
            p.publication_allowed(self.episode, self.meta, self.qa, self.video)

    def test_historical_illustration_label_required(self):
        self.episode["episode_series"] = {
            "historical_reconstruction": True, "chapter": 1,
            "chapter_total": 6,
        }
        self.episode["editorial_references"] = [
            "https://example.org/source-a", "https://example.org/source-b"
        ]
        with self.assertRaisesRegex(ValueError, "documentary"):
            p.publication_allowed(self.episode, self.meta, self.qa, self.video)
        self.meta["description"] += " Иллюстративные кадры."
        self.assertTrue(p.publication_allowed(self.episode, self.meta, self.qa, self.video))


if __name__ == "__main__":
    unittest.main()
