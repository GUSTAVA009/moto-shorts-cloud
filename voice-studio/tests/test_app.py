"""No-GPU FastAPI integration tests with mocked private Qwen model."""
import array
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import wave

os.environ.setdefault("VOICE_STUDIO_DATA","/tmp/gustava-voice-studio-ci")
os.environ.setdefault("VOICE_STUDIO_ADMIN_TOKEN","admin-test-only-"+"x"*32)
os.environ.setdefault("UPSTREAM_API_KEY","internal-test-only-"+"y"*32)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from core import Ledger, VOICE_ID, sha
import app as api

ADMIN={"X-Admin-Token":os.environ["VOICE_STUDIO_ADMIN_TOKEN"]}


def fake_audio():
    # A test tone is never the user's Cartesia file or a real person's voice.
    data=array.array("h",[2600,-2600]*30000)
    output=io.BytesIO()
    with wave.open(output,"wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(24000)
        f.writeframes(data.tobytes())
    return output.getvalue()


class RealWebsiteWithoutGpuTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        api.DATA=Path(self.tmp.name)
        api.LEDGER=Ledger(api.DATA)
        api.VOICE_FILE=api.DATA/"voice-reference-original.wav"
        api.VOICE_PROOF=api.DATA/"voice-reference-original.json"
        self.client=TestClient(api.app)

    def owner_key(self):
        response=self.client.post("/api/admin/keys",json={
            "label":"Real YouTube Factory",
            "max_chars_month":0,
            "max_rpm":12,
        },headers=ADMIN)
        self.assertEqual(response.status_code,201,response.text)
        return response.json()["api_key"]

    def create_original(self):
        with patch.object(api,"qwen_audio",new_callable=AsyncMock) as synth:
            synth.return_value=fake_audio()
            response=self.client.post("/api/admin/voice/design",
                json={"confirm_original":True},headers=ADMIN)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(synth.await_count,1)
            self.assertEqual(synth.await_args.args[0],
                             "/api/v1/voice-design/generate")
            self.assertIn("ORIGINAL",synth.await_args.args[1]["instruct"])
        return response.json()

    def test_ui_is_original_production_site_with_security_headers(self):
        response=self.client.get("/")
        self.assertEqual(response.status_code,200)
        self.assertIn("GUSTAVA VOICE",response.text)
        self.assertIn("Создать озвучку",response.text)
        self.assertEqual(response.headers["x-frame-options"],"DENY")
        self.assertIn("script-src 'self'",response.headers["content-security-policy"])
        for asset in ("/site.css","/site.js"):
            result=self.client.get(asset)
            self.assertEqual(result.status_code,200)
        health=self.client.get("/health").json()
        self.assertFalse(health["reference_available"])
        self.assertFalse(health["audio_generated"])
        self.assertFalse(health["cartesia"])

    def test_admin_required_and_api_keys_never_list_raw_secrets(self):
        self.assertEqual(self.client.get("/api/admin/keys").status_code,401)
        self.assertEqual(self.client.post("/api/admin/keys",json={
            "label":"Unsafe"},headers={"X-Admin-Token":"wrong"}).status_code,401)
        token=self.owner_key()
        listing=self.client.get("/api/admin/keys",headers=ADMIN)
        self.assertEqual(listing.status_code,200)
        self.assertNotIn(token,listing.text)
        self.assertNotIn("token_hash",listing.text)
        keys=listing.json()["keys"]
        self.assertEqual(len(keys),1)
        response=self.client.delete("/api/admin/keys/"+str(keys[0]["id"]),
                                    headers=ADMIN)
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()["revoked"])
        self.assertEqual(self.client.delete("/api/admin/keys/999999",
                                            headers=ADMIN).status_code,404)

    def test_voice_design_is_first_party_original_and_never_overwritten(self):
        denial=self.client.post("/api/admin/voice/design",
            json={"confirm_original":False},headers=ADMIN)
        self.assertEqual(denial.status_code,400)
        self.assertFalse(api.VOICE_FILE.exists())
        created=self.create_original()
        self.assertEqual(created["voice_id"],VOICE_ID)
        proof=json.loads(api.VOICE_PROOF.read_text())
        self.assertFalse(proof["used_cartesia_sample"])
        self.assertEqual(proof["source"],"selfhosted_qwen_voice_design")
        self.assertEqual(proof["wav_sha256"],sha(api.VOICE_FILE.read_bytes()))
        clip=self.client.get("/api/admin/voice/reference",headers=ADMIN)
        self.assertEqual(clip.status_code,200)
        self.assertEqual(clip.content,fake_audio())
        duplicate=self.client.post("/api/admin/voice/design",
                json={"confirm_original":True},headers=ADMIN)
        self.assertEqual(duplicate.status_code,409)
        self.assertEqual(self.client.get("/api/admin/voice",
            headers=ADMIN).json()["reference_sha256"],proof["wav_sha256"])

    def test_one_original_voice_wav_per_idempotency_key(self):
        key=self.owner_key()
        self.create_original()
        text="Сейчас начнётся самое удивительное путешествие на мотоцикле."
        headers={"Authorization":"Bearer "+key,
                 "X-Idempotency-Key":"moto-episode-00001"}
        request={"text":text,"voice":VOICE_ID,"response_format":"wav"}
        with patch.object(api,"qwen_audio",new_callable=AsyncMock) as synth:
            synth.return_value=fake_audio()
            first=self.client.post("/v1/audio/speech",json=request,headers=headers)
            self.assertEqual(first.status_code,200,first.text)
            self.assertEqual(first.content,fake_audio())
            self.assertEqual(first.headers["x-voice-id"],VOICE_ID)
            self.assertEqual(first.headers["x-audio-sha256"],sha(fake_audio()))
            self.assertEqual(synth.await_count,1)
            payload=synth.await_args.args[1]
            self.assertEqual(payload["language"],"Russian")
            self.assertEqual(payload["ref_text"],api.REFERENCE_TEXT)
            self.assertNotIn("https://",str(payload))
            second=self.client.post("/v1/audio/speech",json=request,headers=headers)
            self.assertEqual(second.status_code,200,second.text)
            self.assertEqual(second.content,first.content)
            self.assertEqual(synth.await_count,1)
            changed=dict(request,text=text+" Это другой текст.")
            reject=self.client.post("/v1/audio/speech",json=changed,headers=headers)
            self.assertEqual(reject.status_code,409)
        with api.LEDGER.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM requests").fetchone()[0],1)

    def test_no_api_key_or_original_voice_fails_without_gpu_charge(self):
        key=self.owner_key()
        message={"text":"Настоящая озвучка на своём сервере.","voice":VOICE_ID}
        headers={"Authorization":"Bearer "+key,
                 "X-Idempotency-Key":"short-episode-00003"}
        unauthorized=self.client.post("/v1/audio/speech",json=message,
                                      headers={"X-Idempotency-Key":"test-episode-01"})
        self.assertEqual(unauthorized.status_code,401)
        pending=self.client.post("/v1/audio/speech",json=message,headers=headers)
        self.assertEqual(pending.status_code,503)
        self.assertIn("ORIGINAL_VOICE_NOT_CREATED",pending.text)
        with api.LEDGER.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM requests").fetchone()[0],0)

    def test_unsupported_format_fails_before_usage_and_upstream(self):
        key=self.owner_key();self.create_original()
        response=self.client.post("/v1/audio/speech",
            json={"text":"Текст для теста","response_format":"mp3"},
            headers={"X-API-Key":key,"X-Idempotency-Key":"sample-000099"})
        self.assertEqual(response.status_code,400)
        with api.LEDGER.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM requests").fetchone()[0],0)

    def test_private_backend_cannot_be_redirected_to_third_party(self):
        with patch.object(api,"UPSTREAM","https://cartesia.ai"):
            with self.assertRaisesRegex(RuntimeError,"QWEN_BACKEND_MUST_BE_PRIVATE"):
                api.safe_upstream()
        with patch.object(api,"UPSTREAM","http://qwen:8000"):
            api.safe_upstream()


if __name__=="__main__":
    unittest.main()
