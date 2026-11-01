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
os.environ.setdefault("VOICE_STUDIO_SESSION_SECRET","session-test-only-"+"z"*40)
os.environ.setdefault("UPSTREAM_API_KEY","internal-test-only-"+"y"*32)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from core import Ledger, VOICE_ID, sha
import app as api

ADMIN={"X-Admin-Token":os.environ["VOICE_STUDIO_ADMIN_TOKEN"]}


def fake_audio():
    # A test tone never reproduces any person's voice.
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
        api.LOGIN_ATTEMPTS.clear()
        self.client=TestClient(api.app,base_url="https://voice.example.test")

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

    def owner_login(self):
        response=self.client.post("/auth/login",json={
            "password":ADMIN["X-Admin-Token"]})
        self.assertEqual(response.status_code,200,response.text)
        data=self.client.get("/auth/session")
        self.assertEqual(data.status_code,200,data.text)
        return data.json()["csrf"]

    def test_ui_is_original_production_site_with_security_headers(self):
        # The public internet sees ONLY the login screen, never the studio.
        redirect=self.client.get("/",follow_redirects=False)
        self.assertEqual(redirect.status_code,303)
        self.assertEqual(redirect.headers["location"],"/login")
        self.assertIn("HAPYCH",self.client.get("/login").text)
        for path in ("/site.css","/site.js","/health","/api/admin/voice"):
            self.assertEqual(self.client.get(path).status_code,401,path)
        self.assertEqual(self.client.get("/openapi.json").status_code,404)
        csrf=self.owner_login()
        self.assertEqual(len(csrf),64)
        response=self.client.get("/")
        self.assertEqual(response.status_code,200)
        self.assertIn("HAPYCH",response.text)
        self.assertIn("Мастерская голоса",response.text)
        self.assertIn("Темп речи",response.text)
        self.assertEqual(response.headers["x-frame-options"],"DENY")
        self.assertIn("script-src 'self'",response.headers["content-security-policy"])
        for asset in ("/site.css","/site.js"):
            result=self.client.get(asset)
            self.assertEqual(result.status_code,200)
        health=self.client.get("/health").json()
        self.assertFalse(health["reference_available"])
        self.assertFalse(health["audio_generated"])
        self.assertEqual(health["engine"],"qwen3-tts-selfhosted")


    def test_owner_session_httponly_and_csrf_protect_every_admin_mutation(self):
        # 40+ character signed session cookie; no password stored in JS.
        csrf=self.owner_login()
        cookies=self.client.cookies
        self.assertIn(api.COOKIE,cookies)
        login=self.client.get("/auth/session")
        self.assertNotIn(ADMIN["X-Admin-Token"],login.text)
        no_csrf=self.client.post("/api/admin/keys",json={"label":"Bad key"})
        self.assertEqual(no_csrf.status_code,403)
        wrong_csrf=self.client.post("/api/admin/keys",
            json={"label":"Bad key"},headers={"X-CSRF-Token":"x"*64})
        self.assertEqual(wrong_csrf.status_code,403)
        created=self.client.post("/api/admin/keys",json={"label":"Bot key"},
                                 headers={"X-CSRF-Token":csrf})
        self.assertEqual(created.status_code,201,created.text)
        new_key=created.json()["api_key"]
        self.assertTrue(new_key.startswith("gvk_"))
        logout=self.client.post("/auth/logout",headers={"X-CSRF-Token":csrf})
        self.assertEqual(logout.status_code,200)
        self.assertEqual(self.client.get("/site.js").status_code,401)
        self.assertEqual(self.client.get("/api/admin/keys").status_code,401)
        # Bot key keeps access only to /v1/audio/speech, not administration.
        self.assertEqual(self.client.get("/api/admin/keys",
            headers={"Authorization":"Bearer "+new_key}).status_code,401)

    def test_login_bruteforce_is_limited_and_owner_secret_never_echoed(self):
        for _ in range(api.MAX_LOGINS):
            bad=self.client.post("/auth/login",
                json={"password":"not-the-owner-secret"})
            self.assertEqual(bad.status_code,401)
            self.assertNotIn(ADMIN["X-Admin-Token"],bad.text)
        locked=self.client.post("/auth/login",
            json={"password":ADMIN["X-Admin-Token"]})
        self.assertEqual(locked.status_code,429)
        self.assertEqual(self.client.get("/site.css").status_code,401)

    def test_owner_voice_design_tuning_and_real_qwen_speed_binding(self):
        csrf=self.owner_login()
        with patch.object(api,"qwen_audio",new_callable=AsyncMock) as maker:
            maker.return_value=fake_audio()
            response=self.client.post("/api/admin/voice/design",json={
                "confirm_original":True,
                "timbre":"resonant","delivery":"ironic",
            },headers={"X-CSRF-Token":csrf})
            self.assertEqual(response.status_code,200,response.text)
            instruction=maker.await_args.args[1]["instruct"]
            self.assertIn("resonant cinematic",instruction)
            self.assertIn("natural irony",instruction)
        proof=json.loads(api.VOICE_PROOF.read_text())
        self.assertEqual(proof["design"],{"timbre":"resonant","delivery":"ironic"})
        self.assertEqual(proof["instruction_sha256"],sha(instruction.encode()))
        # Changing the style after pinning is forbidden; no identity drift.
        second=self.client.post("/api/admin/voice/design",json={
            "confirm_original":True,"timbre":"deep",
            "delivery":"documentary",
        },headers={"X-CSRF-Token":csrf})
        self.assertEqual(second.status_code,409)

        key=self.owner_key()
        headers={"Authorization":"Bearer "+key,"X-Idempotency-Key":"moto-short-012345"}
        body={"text":"Наш фирменный голос: проверяем скорость произношения.",
              "voice":VOICE_ID,"speed":1.1,"response_format":"wav"}
        with patch.object(api,"qwen_audio",new_callable=AsyncMock) as maker:
            maker.return_value=fake_audio()
            success=self.client.post("/v1/audio/speech",json=body,headers=headers)
            self.assertEqual(success.status_code,200,success.text)
            self.assertEqual(maker.await_args.args[1]["speed"],1.1)
            self.assertEqual(maker.await_count,1)
            changed=self.client.post("/v1/audio/speech",
                json=dict(body,speed=.90),headers=headers)
            self.assertEqual(changed.status_code,409)
            self.assertEqual(maker.await_count,1)

    def test_two_youtube_channels_get_distinct_speakers_and_isolated_api_keys(self):
        first=self.owner_key()
        with patch.object(api,"qwen_audio",new_callable=AsyncMock) as maker:
            maker.return_value=fake_audio()
            self.create_original()
        new=self.client.post("/api/admin/channels",json={
            "slug":"motorcade","name":"Motorcade Club","timbre":"velvet",
            "delivery":"dynamic"},headers=ADMIN)
        self.assertEqual(new.status_code,201,new.text)
        other_voice=new.json()["voice_id"]
        other_preset=new.json()["speaker_preset"]
        self.assertNotEqual(other_voice,VOICE_ID)
        self.assertNotEqual(other_preset,"eric")
        new_key=self.client.post("/api/admin/keys",json={
            "label":"Motorcade Factory","channel_slug":"motorcade"},
            headers=ADMIN)
        self.assertEqual(new_key.status_code,201,new_key.text)
        second=new_key.json()["api_key"]
        for wrong in [
            {"voice":VOICE_ID,"text":"Чужой голос"},
            {"voice":other_voice,"channel_slug":"gustava","text":"Чужой канал"},
        ]:
            reply=self.client.post("/v1/audio/speech",json=wrong,
              headers={"Authorization":"Bearer "+second,
                       "X-Idempotency-Key":"no-cross-tenant-0001"})
            self.assertEqual(reply.status_code,403,reply.text)
        with patch.object(api,"qwen_audio",new_callable=AsyncMock) as maker:
            maker.return_value=fake_audio()
            ready=self.client.post("/api/admin/voice/design",json={
                "confirm_original":True,"channel_slug":"motorcade",
                "timbre":"velvet","delivery":"dynamic"},headers=ADMIN)
            self.assertEqual(ready.status_code,200,ready.text)
            self.assertEqual(maker.await_args.args[1]["speaker"],other_preset)
        with patch.object(api,"qwen_audio",new_callable=AsyncMock) as synth:
            synth.return_value=fake_audio()
            wav=self.client.post("/v1/audio/speech",json={
                "text":"Настоящий звук второго канала",
                "voice":other_voice,"channel_slug":"motorcade"},
                headers={"Authorization":"Bearer "+second,
                         "X-Idempotency-Key":"only-second-voice-001"})
            self.assertEqual(wav.status_code,200,wav.text)
            self.assertEqual(wav.headers["x-channel-id"],"motorcade")
            self.assertEqual(synth.await_args.args[1]["speaker"],other_preset)
        denied=self.client.post("/v1/audio/speech",json={
            "voice":other_voice,"text":"Дай другой голос"},
            headers={"Authorization":"Bearer "+first,
                     "X-Idempotency-Key":"never-first-gets-second"})
        self.assertEqual(denied.status_code,403)

    def test_actual_cpu_engine_http_payload_and_no_external_request(self):
        class Reply:
            status_code=200
            content=fake_audio()
        called=[]
        class FakeClient:
            def __init__(self,**kwargs):pass
            async def __aenter__(self):return self
            async def __aexit__(self,*args):return False
            async def post(self,url,**kwargs):
                called.append((url,kwargs))
                return Reply()
        with patch.object(api,"UPSTREAM","http://127.0.0.1:8002"), \
             patch.object(api.httpx,"AsyncClient",FakeClient):
            data=__import__("asyncio").run(api.qwen_audio(
                "/api/v1/base/clone",{
                    "text":"Привет, мотоциклы!","speaker":"eric",
                    "delivery":"dynamic","speed":1.1}))
        self.assertEqual(data,fake_audio())
        self.assertEqual(called[0][0],"http://127.0.0.1:8002/v1/tts")
        body=called[0][1]["json"]
        self.assertEqual(body["speaker"],"eric")
        self.assertEqual(body["language"],"Russian")
        self.assertEqual(body["emotion"],"excited")
        self.assertEqual(body["rate"],1.1)

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
        self.assertFalse(proof["exclusive_original_voice"])
        self.assertFalse(proof["derived_from_cartesia"])
        self.assertEqual(proof["source"],"selfhosted_qwen_cpu_preset")
        self.assertEqual(proof["preset_voice"],"eric")
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
        with patch.object(api,"UPSTREAM","https://external-tts.example"):
            with self.assertRaisesRegex(RuntimeError,"QWEN_CPU_ENGINE_MUST_BE_LOOPBACK"):
                api.safe_upstream()
        with patch.object(api,"UPSTREAM","http://127.0.0.1:8002"):
            api.safe_upstream()


if __name__=="__main__":
    unittest.main()
