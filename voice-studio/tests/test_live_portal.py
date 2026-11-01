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
from urllib.request import Request, urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import live_portal as portal


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
            with urlopen(req,timeout=5) as r:
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
              "text":"Текст сценария для тестового прослушивания."}
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
                {"text":"Проверяем автономную приватную русскую озвучку.", "speed":1},
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


if __name__ == "__main__":
    unittest.main()
