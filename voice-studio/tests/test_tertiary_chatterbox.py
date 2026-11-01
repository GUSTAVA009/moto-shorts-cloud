"""No model download: test private Chatterbox API semantics with fake PCM."""
import array
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import tertiary_chatterbox as t


def wav_audio():
    samples=array.array("h",[2600,-2600]*48000)
    output=io.BytesIO()
    with wave.open(output,"wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(24000)
        f.writeframes(samples.tobytes())
    return output.getvalue()


class ChatterboxPrivateFallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.wav=Path(self.tmp.name)/"owner-reference.wav"
        self.wav.write_bytes(wav_audio())
        self.key="gvk_"+"q"*48
        self.env={
            "GUSTAVA_TERTIARY_TTS_ENABLED":"1",
            "GUSTAVA_TERTIARY_VOICE_CANARY_APPROVED":"1",
            "GUSTAVA_TERTIARY_VOICE_API_KEY":self.key,
            "GUSTAVA_TERTIARY_REFERENCE_WAV":str(self.wav),
            "GUSTAVA_VOICE_REFERENCE_SHA256":hashlib.sha256(self.wav.read_bytes()).hexdigest(),
            "GUSTAVA_TERTIARY_CACHE_DIR":str(Path(self.tmp.name)/"cache"),
        }
        patcher=patch.dict(os.environ,self.env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client=TestClient(t.app)
        self.headers={"Authorization":"Bearer "+self.key,
                      "X-Idempotency-Key":"moto-narration-0001"}
        self.body={"voice":t.VOICE_ID,"channel_slug":"gustava",
                   "text":"Сегодня мы проверяем голос мотоблогера.",
                   "response_format":"wav"}

    def test_never_expose_unauthed_audio_or_health(self):
        self.assertEqual(self.client.get("/health").status_code,401)
        self.assertEqual(self.client.post("/v1/audio/speech",json=self.body).status_code,401)
        self.assertEqual(self.client.get("/docs").status_code,404)
        self.assertEqual(self.client.get("/openapi.json").status_code,404)

    def test_pinned_reference_channel_idempotency_and_backend_proof(self):
        with patch.object(t,"_render",return_value=wav_audio()) as fake:
            first=self.client.post("/v1/audio/speech",headers=self.headers,json=self.body)
            self.assertEqual(first.status_code,200,first.text)
            self.assertEqual(first.headers["x-voice-id"],t.VOICE_ID)
            self.assertEqual(first.headers["x-channel-id"],"gustava")
            self.assertEqual(first.headers["x-tts-backend"],t.BACKEND)
            self.assertEqual(first.headers["x-audio-sha256"],hashlib.sha256(first.content).hexdigest())
            self.assertEqual(first.headers["x-reference-sha256"],self.env["GUSTAVA_VOICE_REFERENCE_SHA256"])
            repeat=self.client.post("/v1/audio/speech",headers=self.headers,json=self.body)
            self.assertEqual(repeat.content,first.content)
            fake.assert_called_once()
            conflict=self.client.post("/v1/audio/speech",headers=self.headers,
                                      json=dict(self.body,text="Иной сценарий"))
            self.assertEqual(conflict.status_code,409)

    def test_wrong_channel_or_reference_is_never_silently_used(self):
        with patch.object(t,"_render",return_value=wav_audio()) as fake:
            wrong=self.client.post("/v1/audio/speech",headers=self.headers,
                                   json=dict(self.body,channel_slug="motobratr"))
            self.assertEqual(wrong.status_code,403)
            self.wav.write_bytes(b"modified")
            no_reference=self.client.post("/v1/audio/speech",headers=self.headers,
                                          json=self.body)
            self.assertEqual(no_reference.status_code,503)
            fake.assert_not_called()

    def test_canary_defaults_closed_even_with_key(self):
        with patch.dict(os.environ,{"GUSTAVA_TERTIARY_VOICE_CANARY_APPROVED":"0"}):
            self.assertEqual(self.client.post("/v1/audio/speech",
                headers=self.headers,json=self.body).status_code,503)


if __name__ == "__main__":
    unittest.main()
