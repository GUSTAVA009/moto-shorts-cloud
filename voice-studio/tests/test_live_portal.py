"""Run without network, GPU or model to validate the live isolated portal."""
from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPRedirectHandler

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import live_portal as portal


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None


class LivePortalContract(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        portal.PRIVATE = Path(self.td.name)
        portal.PASSWORD_FILE = portal.PRIVATE / "password.json"
        portal.PREFS_FILE = portal.PRIVATE / "preferences.json"
        portal.AUDIO_DIR = portal.PRIVATE / "previews"
        portal.ensure_dirs()
        portal.atomic_json(portal.PASSWORD_FILE,
                           portal.password_record("a-test-secret-longer-than-14"))
        portal.SESSIONS.clear()
        portal.ATTEMPTS.clear()
        portal.JOBS.clear()
        self.server = ThreadingHTTPServer(("127.0.0.1",0),portal.PortalHandler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = "http://127.0.0.1:%d" % self.server.server_port

    def request(self,method,path,data=None,cookie=None,origin=portal.ORIGIN,csrf=None):
        headers={}
        if data is not None:
            headers["Content-Type"]="application/json"
        if method=="POST" and origin is not None:
            headers["Origin"]=origin
        if cookie is not None:
            headers["Cookie"]=cookie
        if csrf is not None:
            headers["X-CSRF-Token"]=csrf
        body=json.dumps(data).encode() if data is not None else None
        req=Request(self.base+path,data=body,headers=headers,method=method)
        try:
            with build_opener(NoRedirect()).open(req,timeout=5) as r:
                return r.status,r.headers,r.read()
        except HTTPError as exc:
            return exc.code,exc.headers,exc.read()

    def login(self):
        status,headers,_=self.request("POST","/auth/login",{
            "password":"a-test-secret-longer-than-14"})
        self.assertEqual(status,200)
        cookie=headers.get("Set-Cookie")
        self.assertIn("HttpOnly",cookie)
        self.assertIn("SameSite=Strict",cookie)
        self.assertIn("Secure",cookie)
        cookie=cookie.split(";",1)[0]
        status,_,body=self.request("GET","/auth/session",cookie=cookie)
        self.assertEqual(status,200)
        csrf=json.loads(body)["csrf"]
        return cookie,csrf

    def test_login_is_private_and_api_is_separate(self):
        code,headers,_=self.request("GET","/studio")
        self.assertEqual(code,303)
        self.assertEqual(headers["Location"],"/login")
        self.assertEqual(self.request("GET","/api/portal/status")[0],401)
        self.assertEqual(self.request("GET","/api/portal/preferences")[0],401)
        self.assertEqual(self.request("GET","/portal-assets/app.js")[0],401)
        self.assertEqual(self.request("GET","/v1/audio/speech")[0],404)
        code,_,body=self.request("GET","/login")
        self.assertEqual(code,200)
        self.assertIn("Вход в студию",body.decode())
        cookie,csrf=self.login()
        code,headers,body=self.request("GET","/studio",cookie=cookie)
        self.assertEqual(code,200)
        self.assertIn("Мой кабинет",body.decode())
        self.assertEqual(headers["X-Frame-Options"],"DENY")
        self.assertIn("script-src 'self'",headers["Content-Security-Policy"])
        self.assertEqual(self.request("GET","/portal-assets/app.js",cookie=cookie)[0],200)
        code,_,_=self.request("POST","/api/portal/preferences",{
            "channel_name":"GUSTAVA","speed":1,"text":"Ready"},cookie=cookie)
        self.assertEqual(code,403)
        code,_,_=self.request("POST","/api/portal/preferences",{
            "channel_name":"GUSTAVA","speed":1,"text":"Ready"},cookie=cookie,csrf=csrf,
            origin="https://untrusted.example")
        self.assertEqual(code,403)

    def test_owner_can_save_private_preview_preferences(self):
        cookie,csrf=self.login()
        data={"channel_name":"GUSTAVA Enduro","speed":0.95,
              "text":"Текст сценария для тестового прослушивания.",
              "eq":{"80":3,"250":1,"1000":-1,"3000":1,"8000":0}}
        status,_,_=self.request("POST","/api/portal/preferences",
                                data,cookie,csrf=csrf)
        self.assertEqual(status,200)
        code,_,body=self.request("GET","/api/portal/preferences",cookie=cookie)
        self.assertEqual(code,200)
        self.assertEqual(json.loads(body),data)
        self.assertEqual(self.request("POST","/api/portal/preferences",
            {"channel_name":"GUSTAVA","speed":2.0,"text":"x"},
            cookie,csrf=csrf)[0],422)
        self.assertEqual(self.request("POST","/api/portal/preview",
            {"text":"too short","speed":1},
            cookie,csrf=csrf)[0],422)
        # The preview endpoint must not require any new public TTS API key.
        with patch.object(portal,"generate_job",lambda *a:None):
            code,_,body=self.request("POST","/api/portal/preview",
                {"text":"Проверяем автономную приватную русскую озвучку.", "speed":1,
                 "eq":data["eq"]},
                cookie,csrf=csrf)
        self.assertEqual(code,202)
        job=json.loads(body)["job_id"]
        self.assertEqual(len(job),32)
        self.assertEqual(self.request("GET","/api/portal/preview/"+job,cookie=cookie)[0],200)
        self.assertEqual(self.request("GET","/api/portal/preview/"+job)[0],401)

    def test_password_rotates_owner_sessions(self):
        cookie,csrf=self.login()
        code,_,_=self.request("POST","/auth/change-password",{
            "current":"a-test-secret-longer-than-14","next":"new-test-secret-longer-than-14"
        },cookie,csrf=csrf)
        self.assertEqual(code,200)
        self.assertEqual(self.request("GET","/api/portal/status",cookie=cookie)[0],401)
        self.assertTrue(portal.verify_password("new-test-secret-longer-than-14"))
        self.assertFalse(portal.verify_password("a-test-secret-longer-than-14"))

    def test_login_ratelimited_without_content_leak(self):
        for _ in range(7):
            self.assertEqual(self.request("POST","/auth/login",
                {"password":"wrong-test-password"})[0],401)
        self.assertEqual(self.request("POST","/auth/login",
                {"password":"a-test-secret-longer-than-14"})[0],429)


    def test_password_error_codes_and_new_session_csrf_survive_rotation(self):
        cookie,csrf=self.login()
        def change(current,next_value):
            status,headers,raw=self.request("POST","/auth/change-password",
                {"current":current,"next":next_value},cookie,csrf=csrf)
            return status,headers,json.loads(raw)
        self.assertEqual(change("wrong current","long-enough-new-secret-123")[2]["error"],
                         "CURRENT_PASSWORD_INCORRECT")
        self.assertEqual(change("a-test-secret-longer-than-14","too-short")[2]["error"],
                         "NEW_PASSWORD_MIN_14_CHARACTERS")
        self.assertEqual(change("a-test-secret-longer-than-14","a-test-secret-longer-than-14")[2]["error"],
                         "NEW_PASSWORD_MUST_DIFFER")
        self.assertTrue(portal.verify_password("a-test-secret-longer-than-14"))
        status,headers,response=change("a-test-secret-longer-than-14","brand-new-strong-passphrase-2026")
        self.assertEqual(status,200)
        self.assertEqual(response["ok"],True)
        newcsrf=response["csrf"]
        self.assertNotEqual(newcsrf,csrf)
        newcookie=headers["Set-Cookie"].split(";",1)[0]
        old=self.request("GET","/auth/session",cookie=cookie)
        self.assertEqual(old[0],401)
        new=self.request("GET","/auth/session",cookie=newcookie)
        self.assertEqual(new[0],200)
        self.assertEqual(json.loads(new[2])["csrf"],newcsrf)
        payload={"channel_name":"GUSTAVA","text":"after reset","speed":1.0}
        self.assertEqual(self.request("POST","/api/portal/preferences",
            payload,newcookie,csrf=csrf)[0],403)
        self.assertEqual(self.request("POST","/api/portal/preferences",
            payload,newcookie,csrf=newcsrf)[0],200)

    def test_eq_is_bounded_persistent_and_only_affects_preview(self):
        cookie,csrf=self.login()
        flat={"80":0,"250":0,"1000":0,"3000":0,"8000":0}
        deep={"80":3,"250":1,"1000":-1,"3000":1,"8000":0}
        self.assertEqual(portal.voice_filters(1.0,flat),[])
        self.assertEqual(portal.voice_filters(0.95,flat),["atempo=0.95"])
        filters=portal.voice_filters(1.0,deep)
        self.assertIn("equalizer=f=80:t=q:w=1.0:g=3",filters)
        self.assertIn("equalizer=f=1000:t=q:w=1.0:g=-1",filters)
        self.assertIn("alimiter=limit=0.95:level=false",filters)
        for bad in ({**deep, "3000":"1;rm"}, {**deep,"80":19},
                    {**deep,"80":True}, {**deep,"42":0},{}):
            with self.assertRaises(ValueError):
                portal.validate_eq(bad)
            code,_,_=self.request("POST","/api/portal/preferences",{
                "channel_name":"GUSTAVA","speed":1,"text":"test","eq":bad},
                cookie,csrf=csrf)
            self.assertEqual(code,422)
            code,_,_=self.request("POST","/api/portal/preview",{
                "text":"Это осмысленный русский тест для эквалайзера.",
                "speed":1,"eq":bad},cookie,csrf=csrf)
            self.assertEqual(code,422)
        code,_,body=self.request("GET","/api/portal/preferences",cookie=cookie)
        self.assertEqual(code,200)
        self.assertEqual(json.loads(body)["eq"],flat)
        payload={"channel_name":"GUSTAVA","speed":1.0,"text":"test","eq":deep}
        self.assertEqual(self.request("POST","/api/portal/preferences",payload,cookie,csrf=csrf)[0],200)
        self.assertEqual(json.loads(self.request("GET","/api/portal/preferences",
                          cookie=cookie)[2])["eq"],deep)
        # Existing pre-upgrade tab must continue to work without resetting EQ.
        legacy={"channel_name":"GUSTAVA","speed":1.0,"text":"old tab"}
        self.assertEqual(self.request("POST","/api/portal/preferences",legacy,cookie,csrf=csrf)[0],200)
        self.assertEqual(json.loads(self.request("GET","/api/portal/preferences",
                          cookie=cookie)[2])["eq"],deep)
        with patch.object(portal,"generate_job",lambda *a:None):
            status,_,body=self.request("POST","/api/portal/preview",{
                "text":"Готовим новую озвучку на сервере для прослушивания.",
                "speed":1.0,"eq":deep},cookie,csrf=csrf)
        self.assertEqual(status,202)
        job_id=json.loads(body)["job_id"]
        self.assertEqual(len(job_id),32)
        # No production voice profile or source reference is mutable here.
        self.assertEqual(portal.VOICE_ID,"gustava-original-v1")
        self.assertEqual(len(portal.REF_SHA),64)

    def test_ffmpeg_equalizer_changes_real_pcm_when_ffmpeg_available(self):
        """Confirm actual signal processing, not just the sliders/filter text."""
        import array
        import io
        import math
        import shutil
        import subprocess
        import wave
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg is installed on owner production VPS, not every CI runner")
        rate=24000
        frames=array.array("h")
        for i in range(rate * 2):
            value=int(32767*(0.18*math.sin(2*math.pi*80*i/rate) +
                             0.06*math.sin(2*math.pi*1000*i/rate)))
            frames.append(value)
        source=self.td.name+"/source.wav"
        output=self.td.name+"/processed.wav"
        with wave.open(source,"wb") as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(rate)
            f.writeframes(frames.tobytes())
        filters=portal.voice_filters(1.0,
                    {"80":4,"250":0,"1000":0,"3000":0,"8000":0})
        subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error",
                        "-y","-i",source,"-filter:a",",".join(filters),
                        "-ar","24000","-ac","1","-c:a","pcm_s16le",output],
                       capture_output=True,check=True,timeout=30)
        with wave.open(output,"rb") as wav:
            self.assertEqual(wav.getnchannels(),1)
            self.assertEqual(wav.getframerate(),rate)
            self.assertEqual(wav.getsampwidth(),2)
            filtered=array.array("h")
            filtered.frombytes(wav.readframes(wav.getnframes()))
        self.assertNotEqual(frames[:2000],filtered[:2000])
        self.assertLess(max(abs(v) for v in filtered),31500)
        def frequency_power(signal,freq):
            # One complete second gives orthogonal 80 Hz and 1 kHz harmonics.
            size=rate
            cos=sum(signal[i]*math.cos(2*math.pi*freq*i/rate)
                    for i in range(size))
            sin=sum(signal[i]*math.sin(2*math.pi*freq*i/rate)
                    for i in range(size))
            return (cos*cos+sin*sin)**0.5 / size
        self.assertGreater(frequency_power(filtered,80),
                           frequency_power(frames,80)*1.25)


if __name__ == "__main__":
    unittest.main()
