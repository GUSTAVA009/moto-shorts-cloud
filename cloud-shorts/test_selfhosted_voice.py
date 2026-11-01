"""Cloud-only original Qwen TTS guard tests; never send a live HTTP request."""
import array
import io
import json
import tempfile
import unittest
import wave
from pathlib import Path

import selfhosted_voice as q


def synthetic_pcm(seconds=4.0,rate=24000):
    output=io.BytesIO()
    samples=array.array("h",[3600,-3600]*int(rate*seconds/2))
    with wave.open(output,"wb") as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(rate)
        wav.writeframes(samples.tobytes())
    return output.getvalue()


class OriginalPrivateCloudTtsTests(unittest.TestCase):
    def setUp(self):
        self.env={
            "GUSTAVA_VOICE_API_URL":"https://voice.hapychrust.ru/v1/audio/speech",
            "GUSTAVA_VOICE_APPROVED_HOST":"voice.hapychrust.ru",
            "GUSTAVA_SELFHOSTED_TTS_ENABLED":"1",
            "GUSTAVA_VOICE_KEY_PRESENT":"true",
            "GUSTAVA_VOICE_REFERENCE_SHA256":"a"*64
        }
        self.ep={"id":"motorcycle-00017","voice_engine":q.VOICE_ENGINE,
                 "voice_profile":q.PROFILE_ID,
                 "selfhosted_voice_id":q.VOICE_ID,
                 "narration":"Дорога уводит нас далеко. Сегодня мы сравним "
                             "разные мотоциклы. Всё начинается с одного шага.",
                 "auto_publish":False}

    def test_only_own_https_whitelisted_host(self):
        self.assertEqual(q.valid_url(self.env),self.env["GUSTAVA_VOICE_API_URL"])
        bad=[
            "http://voice.hapychrust.ru/v1/audio/speech",
            "https://voice.hapychrust.ru.evil.org/v1/audio/speech",
            "https://another-host.example/v1/audio/speech",
            "https://voice.hapychrust.ru/v1/audio/speech?leak=yes",
            "https://token@voice.hapychrust.ru/v1/audio/speech",
            "https://voice.hapychrust.ru:8080/v1/audio/speech",
            "https://voice.hapychrust.ru/v1/audio/speech/",
        ]
        for url in bad:
            with self.subTest(url=url):
                with self.assertRaisesRegex(ValueError,"UNAPPROVED_HTTPS_HOST"):
                    q.valid_url(dict(self.env,GUSTAVA_VOICE_API_URL=url))

    def test_only_explicit_inference_enablement_and_reference_hash(self):
        self.assertTrue(q.ready(self.ep,self.env))
        for key,value in [
            ("GUSTAVA_SELFHOSTED_TTS_ENABLED","0"),
            ("GUSTAVA_VOICE_KEY_PRESENT","false"),
            ("GUSTAVA_VOICE_REFERENCE_SHA256","not-a-sha"),
        ]:
            with self.subTest(key=key):
                self.assertFalse(q.ready(self.ep,dict(self.env,**{key:value})))
        self.assertFalse(q.ready(dict(self.ep,auto_publish=True),self.env))
        self.assertFalse(q.ready(dict(self.ep,selfhosted_voice_id="other"),self.env))
        self.assertFalse(q.ready(dict(self.ep,voice_engine="cartesia_sonic36"),self.env))

    def test_real_wav_header_duration_and_no_fake_invented_bytes(self):
        self.assertAlmostEqual(q.valid_source_wav(synthetic_pcm()),4.0)
        for raw in [b"not a wav",b"RIFF0000WAVE",synthetic_pcm(seconds=1.0),
                    synthetic_pcm(seconds=55.0),synthetic_pcm()[:500]]:
            with self.assertRaises(ValueError):
                q.valid_source_wav(raw)

    def test_hash_pinned_original_identity_and_audio_qa_receipts(self):
        from deep_voice import provenance_path, pcm_stats
        with tempfile.TemporaryDirectory() as td:
            wav=Path(td)/"voice.wav"
            wav.write_bytes(synthetic_pcm())
            stats=pcm_stats(wav)
            receipt={
                "episode_id":self.ep["id"],
                "voice_engine":q.VOICE_ENGINE,
                "voice_profile":q.PROFILE_ID,
                "voice_id":q.VOICE_ID,
                "text_sha256":q.sha(self.ep["narration"].encode("utf8")),
                "source_audio_sha256":"b"*64,
                "reference_sha256":"a"*64,
                "wav_sha256":q.sha(wav.read_bytes()),
                "duration_seconds":stats["duration_seconds"]
            }
            provenance_path(wav).write_text(json.dumps(receipt),encoding="utf8")
            self.assertEqual(q.verify_profile(wav,self.ep)["reference_sha256"],
                             "a"*64)
            wav.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError,"PROVENANCE_MISMATCH"):
                q.verify_profile(wav,self.ep)


if __name__=="__main__":
    unittest.main()
