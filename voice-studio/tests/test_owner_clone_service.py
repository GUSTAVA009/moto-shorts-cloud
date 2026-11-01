"""Offline security and actual WAV-payload tests for owner Qwen CPU TTS API."""
import contextlib
import hashlib
from http.server import ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import wave

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import owner_clone_service as api


def pcm_wav():
    raw=io.BytesIO()
    with wave.open(raw,"wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        import array
        w.writeframes(array.array("h",[2400,-2000]*42000).tobytes())
    return raw.getvalue()


class OwnerCloneServiceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        (root/"engine"/"qwen3-tts-0.6b-base").mkdir(parents=True)
        (root/"engine"/"qwen_tts").write_bytes(b"fake-engine")
        (root/"private").mkdir()
        (root/"private"/"owner-approved-deep-reference.wav").write_bytes(pcm_wav())
        self.env={
           "OWNER_TTS_ROOT":str(root),
           "GUSTAVA_VOICE_REFERENCE_SHA256":hashlib.sha256(pcm_wav()).hexdigest(),
           "OWNER_TTS_API_KEY":"gvk_"+"a"*48,
           "OWNER_TTS_ALLOW_GITHUB_OIDC":"1",
        }
        self.patch=patch.dict(os.environ,self.env)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.request={"text":"Привет, это реальный тест русского голоса.",
                      "voice":api.VOICE_ID,"channel_slug":"gustava",
                      "response_format":"wav"}
        self.root=root

    def test_invalid_issuer_source_or_workflow_never_authorized(self):
        good={"repository_id":api.REPO_ID,"repository":api.REPO_NAME,
              "ref":api.REQUIRED_REF,"workflow_ref":api.ALLOWED_WORKFLOWS[0]}
        self.assertTrue(api.validate_actions_claims(good))
        for patchdata in (
           {"repository_id":"0000000"},
           {"repository":"attacker/moto-shorts-cloud"},
           {"ref":"refs/pull/80/merge"},
           {"workflow_ref":"attacker/other/.github/workflows/daily-preview.yml@refs/heads/main"},
           {"workflow_ref":"GUSTAVA009/moto-shorts-cloud/.github/workflows/evil.yml@refs/heads/main"},
        ):
            with self.subTest(patchdata=patchdata),self.assertRaises(PermissionError):
                api.validate_actions_claims(dict(good,**patchdata))

    def test_pin_and_validate_speaker_reference(self):
        self.assertEqual(api.paths()[-1],self.env["GUSTAVA_VOICE_REFERENCE_SHA256"])
        with patch.dict(os.environ,{"GUSTAVA_VOICE_REFERENCE_SHA256":"f"*64}):
            with self.assertRaisesRegex(RuntimeError,"REFERENCE_SHA_CHANGED"):
                api.paths()

    def test_cache_reuses_only_identical_transcript_and_checks_wav(self):
        seen=[]
        def producer(text,tmp,root,engine,model,ref):
            seen.append(text)
            return pcm_wav()
        first,_=api.build_audio(self.request,"factory-test-0001",producer=producer)
        repeat,_=api.build_audio(self.request,"factory-test-0001",producer=producer)
        self.assertEqual(first,repeat)
        self.assertEqual(len(seen),1)
        with self.assertRaisesRegex(ValueError,"IDEMPOTENCY_COLLISION"):
            api.build_audio(dict(self.request,text="Другой текст для проверки повторного запроса."),
                            "factory-test-0001",producer=producer)
        self.assertEqual(len(seen),1)

    def test_audio_cannot_be_silent_or_missing(self):
        with self.assertRaises(ValueError):
            api.wav_checked(b"not a wav")
        import array
        raw=io.BytesIO()
        with wave.open(raw,"wb") as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000)
            w.writeframes(array.array("h",[0]*96000).tobytes())
        with self.assertRaisesRegex(ValueError,"SILENT"):
            api.wav_checked(raw.getvalue())
        with self.assertRaises(ValueError):
            api.build_audio(self.request,"factory-0002",
                producer=lambda *args: b"")

    def test_strict_request_shape_and_owner_key(self):
        self.assertEqual(api.authorize("Bearer "+self.env["OWNER_TTS_API_KEY"]),"owner_key")
        with self.assertRaises(PermissionError):
            api.authorize("Bearer wrong-secret")
        with self.assertRaises(PermissionError):
            api.validate_request(dict(self.request,voice="silero"),"factory-0003")
        with self.assertRaises(ValueError):
            api.validate_request(dict(self.request,extra="injected"),"factory-0004")
        with self.assertRaises(ValueError):
            api.validate_request(self.request,"../../../evil")

    def test_loopback_http_never_returns_audio_without_owner_auth(self):
        app=ThreadingHTTPServer(("127.0.0.1",0),api.Handler)
        thread=threading.Thread(target=app.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(app.server_close)
        self.addCleanup(app.shutdown)
        url="http://127.0.0.1:"+str(app.server_address[1])+"/v1/audio/speech"
        body=json.dumps(self.request,ensure_ascii=False).encode("utf8")
        request=urllib.request.Request(url,data=body,method="POST",
             headers={"X-Idempotency-Key":"factory-0003","Content-Type":"application/json"})
        with self.assertRaises(urllib.error.HTTPError) as blocked:
            urllib.request.urlopen(request,timeout=3)
        self.assertEqual(blocked.exception.code,403)
        with patch.object(api,"production_run",return_value=pcm_wav()):
            authed=urllib.request.Request(url,data=body,method="POST",
                headers={"X-Idempotency-Key":"factory-0003",
                         "Content-Type":"application/json",
                         "Authorization":"Bearer "+self.env["OWNER_TTS_API_KEY"]})
            with urllib.request.urlopen(authed,timeout=5) as r:
                self.assertEqual(r.status,200)
                self.assertEqual(r.headers["X-Audio-SHA256"],
                                 hashlib.sha256(r.read()).hexdigest())
                self.assertEqual(r.headers["X-Voice-ID"],api.VOICE_ID)
                self.assertEqual(r.headers["X-Channel-ID"],api.CHANNEL)

if __name__=="__main__":
    unittest.main()
