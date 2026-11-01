"""Vendor-independent publication QA tests: no network, no posting."""
import tempfile
import hashlib
from deep_voice import PUBLIC_ATTRIBUTION
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
            "voice_engine": "aidocmaker_deep",
            "title": "Мотокросс: крутой подъём",
            "narration": "Райдер на мотоцикле преодолевает препятствия.",
            "editorial": {"bike": "offroad-motorcycle"},
            "footage": [{"license": "Pexels License"}],
        }
        self.episode["deep_audio"] = {"provider":"aidocmaker.com", "voice_id":"deep",
          "preview_url":"https://storage.googleapis.com/adm--audio-playback--7d--public/mcp-preview/59b382df-d33f-45d2-943d-22f1db747299.mp3",
          "transcript_sha256":hashlib.sha256(self.episode["narration"].encode()).hexdigest(),
          "source_audio_sha256":"a"*64}
        self.meta = {
            "episode_id": self.episode["id"],
            "title": self.episode["title"],
            "description": "Новые мотосцены, оригинальная озвучка.\n\n" + PUBLIC_ATTRIBUTION,
        }
        self.qa = {
            "episode_id": self.episode["id"],
            "passed": True, "status": "passed",
            "lexical_coverage": .99, "ending_coverage": .99,
            "final_word_present": True, "male_voice_verified": True,
            "voice_profile": "gustava_create_audio_deep_v1",
            "voice_speaker": "deep", "voice_provider": "aidocmaker.com",
            "voice_source_audio_sha256": "a"*64,
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

    def set_cartesia_voice(self):
        from cartesia_voice import VOICE_ENGINE, PROFILE_ID, MODEL_ID
        voice_id = "0f111c12-cabc-4ba0-9a29-1ef98b133e90"
        self.episode["voice_engine"] = VOICE_ENGINE
        self.episode["voice_profile"] = PROFILE_ID
        self.episode["cartesia_voice_id"] = voice_id
        self.episode.pop("deep_audio", None)
        self.meta["description"] = "Оригинальный мотоконтент с русской озвучкой."
        self.qa.update({
            "voice_profile": PROFILE_ID,
            "voice_speaker": voice_id,
            "voice_provider": "cartesia.ai",
            "voice_model_id": MODEL_ID,
            "voice_source_audio_sha256": "b" * 64,
        })

    def test_cartesia_free_or_unlicensed_voice_cannot_publish(self):
        from unittest.mock import patch
        self.set_cartesia_voice()
        with patch.dict("os.environ", {"CARTESIA_COMMERCIAL_PLAN_CONFIRMED": "0"}):
            with self.assertRaisesRegex(ValueError, "CARTESIA_COMMERCIAL_RIGHTS"):
                p.publication_allowed(self.episode, self.meta,
                                      self.qa, self.video)
        with patch.dict("os.environ", {"CARTESIA_COMMERCIAL_PLAN_CONFIRMED": "1"}):
            self.assertTrue(p.publication_allowed(self.episode, self.meta,
                                                 self.qa, self.video))
            for field in ("voice_speaker", "voice_provider", "voice_model_id",
                          "voice_source_audio_sha256"):
                original=self.qa[field]
                self.qa[field]="unknown"
                try:
                    with self.assertRaisesRegex(ValueError, "CARTESIA_GENUINE"):
                        p.publication_allowed(self.episode,self.meta,
                                              self.qa,self.video)
                finally:
                    self.qa[field]=original
            self.qa["voice_profile"] = "old-male-voice"
            with self.assertRaisesRegex(ValueError, "CARTESIA_GENUINE"):
                p.publication_allowed(self.episode,self.meta,
                                      self.qa,self.video)

    def test_valid_motorcycle_clip(self):
        self.assertTrue(p.publication_allowed(self.episode, self.meta, self.qa, self.video))

    def test_old_voice_profile_never_passes_publication(self):
        self.qa.pop("male_voice_verified")
        with self.assertRaisesRegex(ValueError, "ONLY_APPROVED_CREATE_AUDIO_DEEP"):
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

    def test_owner_rejected_and_unreviewed_scene_first_video_blocked(self):
        self.episode["visual_review_failed"]=True
        with self.assertRaisesRegex(ValueError,"OWNER_REJECTED_VISUALS"):
            p.publication_allowed(self.episode,self.meta,self.qa,self.video)
        self.episode.pop("visual_review_failed")
        self.episode["visual_director_version"]=3
        with self.assertRaisesRegex(ValueError,"SCENE_FIRST_REVIEW_REQUIRED"):
            p.publication_allowed(self.episode,self.meta,self.qa,self.video)

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
