"""Real owner-only voice auditions: API + WAV/MP3 manifest not public."""
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import live_portal as portal
from voice_cast_library import ROLE_IDS, MODEL

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None

class PortalCastLiveIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.cast_root=self.root/"audition"
        (self.cast_root/"by_role").mkdir(parents=True)
        payload={"model":MODEL,"source_count":9,"role_variants":17,
                 "production_enabled":False,"voices":[]}
        for index,role in enumerate(sorted(ROLE_IDS),1):
            name=f"{index:02d}_{role}.mp3"
            data=b"ID3"+bytes([index])*1500
            (self.cast_root/"by_role"/name).write_bytes(data)
            payload["voices"].append({
                "id":role,"name_ru":"Тест "+role,"speaker":"ryan",
                "mp3_file":name,"sha256_mp3":hashlib.sha256(data).hexdigest(),
                "pitch_semitones":-2 if role=="cartoon_spring_nasal_original_v1" else 0,
                "seconds":5.7,"asr_passed":True,"production_enabled":False,
                "sha256_wav":"1"*64,
                "asr_check":{"engine":"faster-whisper-small-cpu-int8",
                    "audio_sha256":"1"*64,"coverage":1.0,"precision":1.0}})
        (self.cast_root/"voice_pack_manifest.json").write_text(json.dumps(payload),"utf8")
        p=patch.dict(os.environ,{"HAPYCH_CAST_AUDITION_ROOT":str(self.cast_root)})
        p.start();self.addCleanup(p.stop)
        portal.PRIVATE=self.root/"portal"
        portal.PASSWORD_FILE=portal.PRIVATE/"password.json"
        portal.PREFS_FILE=portal.PRIVATE/"preferences.json"
        portal.AUDIO_DIR=portal.PRIVATE/"previews"
        portal.ensure_dirs()
        portal.atomic_json(portal.PASSWORD_FILE,
            portal.password_record("secure-test-owner-password-2026"))
        portal.SESSIONS.clear()
        portal.ATTEMPTS.clear()
        portal.JOBS.clear()
        self.server=ThreadingHTTPServer(("127.0.0.1",0),portal.PortalHandler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url="http://127.0.0.1:"+str(self.server.server_port)

    def request(self,path,method="GET",data=None,cookie=None):
        headers={}
        if cookie:headers["Cookie"]=cookie
        if data is not None:
            headers["Origin"]=portal.ORIGIN
            headers["Content-Type"]="application/json"
        raw=json.dumps(data).encode() if data is not None else None
        req=Request(self.url+path,method=method,data=raw,headers=headers)
        try:
            with build_opener(NoRedirect()).open(req,timeout=4) as res:
                return res.status,res.headers,res.read()
        except HTTPError as e:
            return e.code,e.headers,e.read()

    def login(self):
        code,headers,_=self.request("/auth/login","POST",{
            "password":"secure-test-owner-password-2026"})
        self.assertEqual(code,200)
        return headers["Set-Cookie"].split(";",1)[0]

    def test_owner_can_list_and_listen_real_voice_only_inside_session(self):
        self.assertEqual(self.request("/api/portal/cast")[0],401)
        self.assertEqual(self.request("/api/portal/cast/father/audio")[0],401)
        cookie=self.login()
        code,headers,body=self.request("/api/portal/cast",cookie=cookie)
        self.assertEqual(code,200)
        info=json.loads(body)
        self.assertEqual(info["count"],17)
        self.assertEqual(info["production_approved"],0)
        self.assertEqual(info["short_russian_canary_passed"],17)
        self.assertEqual(info["independent_stock_speakers"],9)
        self.assertFalse(any(x["production_enabled"] for x in info["voices"]))
        code,headers,data=self.request("/api/portal/cast/father/audio",cookie=cookie)
        self.assertEqual(code,200)
        self.assertEqual(headers.get_content_type(),"audio/mpeg")
        self.assertTrue(data.startswith(b"ID3"))
        self.assertIn("no-store",headers["Cache-Control"])
        self.assertEqual(self.request("/api/portal/cast/../../private/audio")[0],401)
        self.assertEqual(self.request("/api/portal/cast/notexistent/audio",cookie=cookie)[0],404)
        self.assertEqual(self.request("/api/portal/cast/father/audio?ignored=1",cookie=cookie)[0],200)
        self.assertEqual(portal.VOICE_ID,"gustava-original-v1")

    def test_replaced_or_mismatched_audio_file_not_served(self):
        cookie=self.login()
        entry=next(x for x in json.loads((self.cast_root/"voice_pack_manifest.json").read_text())["voices"] if x["id"]=="father")
        f=self.cast_root/"by_role"/entry["mp3_file"]
        f.write_bytes(b"ID3"+"changed".encode()*400)
        self.assertEqual(self.request("/api/portal/cast",cookie=cookie)[0],503)
        self.assertEqual(self.request("/api/portal/cast/father/audio",cookie=cookie)[0],404)
        self.assertEqual(self.request("/api/portal/cast",cookie=None)[0],401)

if __name__ == "__main__":
    unittest.main()
