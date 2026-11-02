"""The selected-voice UI never exposes files to anonymous viewers."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import live_portal as portal
from owner_voice_selection import SelectionUnavailable

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None

class SelectedVoiceRoutes(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        portal.PRIVATE=Path(t.name)
        portal.PASSWORD_FILE=portal.PRIVATE/"password.json"
        portal.PREFS_FILE=portal.PRIVATE/"preferences.json"
        portal.AUDIO_DIR=portal.PRIVATE/"previews"
        portal.ensure_dirs()
        portal.atomic_json(portal.PASSWORD_FILE,portal.password_record(
             "owner-strong-passphrase-for-the-test"))
        portal.SESSIONS.clear();portal.ATTEMPTS.clear();portal.JOBS.clear()
        self.server=ThreadingHTTPServer(("127.0.0.1",0),portal.PortalHandler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.base="http://127.0.0.1:"+str(self.server.server_port)

    def request(self,path,method="GET",payload=None,cookie=None):
        h={}
        if cookie:h["Cookie"]=cookie
        if payload is not None:
            h["Content-Type"]="application/json";h["Origin"]=portal.ORIGIN
        req=Request(self.base+path,method=method,headers=h,
                    data=json.dumps(payload).encode() if payload is not None else None)
        try:
            with build_opener(NoRedirect()).open(req,timeout=4) as r:
                return r.status,r.headers,r.read()
        except HTTPError as e:return e.code,e.headers,e.read()

    def login(self):
        code,h,_=self.request("/auth/login","POST",
             {"password":"owner-strong-passphrase-for-the-test"})
        self.assertEqual(code,200)
        return h["Set-Cookie"].split(";",1)[0]

    def test_new_voice_selection_private_playback(self):
        cookie=self.login()
        fake={"selected_count":3,"original_cartoon_candidates":1,
              "production_approved_count":0,"original_deep_unchanged":True,
              "voices":[{"id":"mother"},{"id":"grandma"},{"id":"warm_biker_woman"},
                         {"id":"cartoon_bubble_v2_b"}]}
        with patch.object(portal,"owner_voice_list",return_value=fake),patch.object(
            portal,"owner_voice_bytes",return_value=(b"ID3"+bytes(2400),"audio/mpeg","CARTOON_BUBBLE_V2_B.mp3")) as call:
            self.assertEqual(self.request("/api/portal/selected-voices")[0],401)
            self.assertEqual(self.request("/api/portal/selected-voices/mother/audio")[0],401)
            c,_,body=self.request("/api/portal/selected-voices",cookie=cookie)
            self.assertEqual(c,200)
            self.assertEqual(json.loads(body)["selected_count"],3)
            code,h,content=self.request("/api/portal/selected-voices/cartoon_bubble_v2_b/audio",cookie=cookie)
            self.assertEqual(code,200)
            self.assertEqual(h.get_content_type(),"audio/mpeg")
            self.assertEqual(content[:3],b"ID3")
            self.assertIn("no-store",h["Cache-Control"])
            call.assert_called_once_with("cartoon_bubble_v2_b")
            self.assertEqual(portal.VOICE_ID,"gustava-original-v1")

    def test_missing_audio_denied_not_silently_swapped(self):
        cookie=self.login()
        with patch.object(portal,"owner_voice_bytes",side_effect=SelectionUnavailable("no file")):
            code,h,content=self.request("/api/portal/selected-voices/father/audio",cookie=cookie)
            self.assertEqual(code,404)
        with patch.object(portal,"owner_voice_list",side_effect=SelectionUnavailable("SHA mismatch")):
            code,h,body=self.request("/api/portal/selected-voices",cookie=cookie)
            self.assertEqual(code,503)
        self.assertEqual(self.request("/api/portal/selected-voices/../../private/owner-tts.env",cookie=cookie)[0],404)

if __name__=="__main__":
    unittest.main()
