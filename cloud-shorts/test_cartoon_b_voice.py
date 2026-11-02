"""Owner-approved Cartoon B: strict voice identity on future Shorts, old DEEP untouched."""
import array
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

import voice_routing
import voice_failover
import selfhosted_voice as voice
import find_pending_publication as pending
from deep_voice import provenance_path,pcm_stats


def valid_wav():
    dst=io.BytesIO()
    with wave.open(dst,"wb") as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(24000)
        f.writeframes(array.array("h",[2000,-2300]*48000).tobytes())
    return dst.getvalue()


class CartoonBProductionTests(unittest.TestCase):
    def setUp(self):
        self.env={
            "GUSTAVA_SELFHOSTED_TTS_ENABLED":"1",
            "GUSTAVA_VOICE_KEY_PRESENT":"true",
            "GUSTAVA_VOICE_API_URL":"https://voice.hapychrust.ru/v1/audio/speech",
            "GUSTAVA_VOICE_APPROVED_HOST":"voice.hapychrust.ru",
        }
        self.ep={
            "id":"moto-cartoon-b-001",
            **voice_routing.new_episode_configuration({}),
            "auto_preview":True,"auto_publish":False,
            "narration":"На этом трэке райдер уже проверил тормоза. Скоро начинаем тренировку!",
            "title":"Мотоцикл проходит трек",
            "editorial":{"bike":"motocross-bike"},
        }

    def test_B_chosen_for_all_new_unattended_originals(self):
        self.assertEqual(self.ep["voice_engine"],voice.VOICE_ENGINE)
        self.assertEqual(self.ep["voice_profile"],voice.CARTOON_B_PROFILE_ID)
        self.assertEqual(self.ep["selfhosted_voice_id"],voice.CARTOON_B_VOICE_ID)
        self.assertEqual(voice.profile_for_episode(self.ep),voice.CARTOON_B_PROFILE_ID)
        self.assertTrue(voice.ready(self.ep,self.env))
        self.assertEqual(voice.reference_for_episode(self.ep,self.env),
                         voice.CARTOON_B_REFERENCE_SHA)
        self.assertEqual(len(voice_failover.available_routes(
            self.env,voice_id=voice.CARTOON_B_VOICE_ID)),1)
        self.assertEqual(voice_failover.available_routes(
            self.env,voice_id=voice.CARTOON_B_VOICE_ID)[0].expected_backend,
            voice.CARTOON_B_BACKEND)
        self.assertEqual(voice_failover.available_routes(
            self.env,voice_id=voice.CARTOON_B_VOICE_ID)[0].name,"cloud")

    def test_old_profile_cannot_masquerade_as_B(self):
        self.assertFalse(voice.approved_profile(dict(self.ep,selfhosted_voice_id=voice.VOICE_ID)))
        self.assertFalse(voice.approved_profile(dict(self.ep,voice_profile=voice.PROFILE_ID)))
        self.assertFalse(voice.ready(dict(self.ep,voice_profile="made_up"),self.env))
        self.assertFalse(voice.ready(dict(self.ep,auto_publish=True),self.env))
        self.assertFalse(voice.ready(self.ep,dict(self.env,GUSTAVA_VOICE_API_URL=
             "https://unrelated.example/v1/audio/speech")))
        self.assertEqual(voice_failover.available_routes(
             self.env,voice_id="silero-old"),())

    def test_B_audio_provenance_must_match_B_SHA_and_profile(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/"voice.wav"
            target.write_bytes(valid_wav())
            stats=pcm_stats(target)
            proof={
                "episode_id":self.ep["id"],
                "voice_engine":voice.VOICE_ENGINE,
                "voice_profile":voice.CARTOON_B_PROFILE_ID,
                "voice_id":voice.CARTOON_B_VOICE_ID,
                "text_sha256":hashlib.sha256(
                    self.ep["narration"].encode()).hexdigest(),
                "spoken_text_sha256":hashlib.sha256(
                    __import__("pronunciation_ru").to_speech_text(
                    self.ep["narration"]).encode()).hexdigest(),
                "source_audio_sha256":"1"*64,
                "reference_sha256":voice.CARTOON_B_REFERENCE_SHA,
                "wav_sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
                "duration_seconds":stats["duration_seconds"]
            }
            provenance_path(target).write_text(json.dumps(proof),encoding="utf8")
            self.assertEqual(voice.verify_profile(target,self.ep)["voice_id"],
                             voice.CARTOON_B_VOICE_ID)
            proof["reference_sha256"]="a"*64
            provenance_path(target).write_text(json.dumps(proof),encoding="utf8")
            with self.assertRaises(ValueError):
                voice.verify_profile(target,self.ep)

    def test_must_match_B_on_final_buffer_selector(self):
        ep=dict(self.ep,auto_publish=True)
        receipt={
            "id":ep["id"],"state":"preview_ready",
            "voice_profile":voice.CARTOON_B_PROFILE_ID,
            "selfhosted_voice_id":voice.CARTOON_B_VOICE_ID,
            "selfhosted_reference_sha256":voice.CARTOON_B_REFERENCE_SHA,
            "male_voice_verified":True,"voice_qa_passed":True,
            "mixed_audio_qa_passed":True,"run_id":"10101"
        }
        art=[{"name":"daily-preview-"+ep["id"]+"-10101","expired":False}]
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(pending.select({"episodes":[ep]},[receipt],set(),art),
                             (10101,ep["id"],art[0]["name"]))
            self.assertIsNone(pending.select({"episodes":[ep]},[
                dict(receipt,selfhosted_reference_sha256="f"*64)],set(),art))
            self.assertIsNone(pending.select({"episodes":[ep]},[
                dict(receipt,voice_qa_passed=False)],set(),art))
            self.assertIsNone(pending.select({"episodes":[ep]},[receipt],{ep["id"]},art))
            self.assertIsNone(pending.select({"episodes":[dict(ep,auto_publish=False)]},
                [receipt],set(),art))

if __name__=="__main__":
    unittest.main()
