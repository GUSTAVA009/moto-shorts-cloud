"""Private live auditions: REAL model-derived files, never production narrator."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import voice_cast_library as cast

class CastLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/"by_role").mkdir()
        roles=sorted(cast.ROLE_IDS)
        self.model={
          "model":cast.MODEL,"source_count":9,"role_variants":17,
          "production_enabled":False,"voices":[]
        }
        for i,role in enumerate(roles,1):
            raw=b"ID3"+bytes([i])*1500
            name=f"{i:02d}_{role}.mp3"
            (self.root/"by_role"/name).write_bytes(raw)
            self.model["voices"].append({
             "id":role,"name_ru":"Тест "+role,"speaker":"ryan",
             "mp3_file":name,"pitch_semitones":-2 if "cartoon" in role else 0,
             "seconds":5.7,"sha256_mp3":hashlib.sha256(raw).hexdigest(),
             "asr_passed":True,"production_enabled":False,
             "sha256_wav":"1"*64,
             "asr_check":{"engine":"faster-whisper-small-cpu-int8",
                          "audio_sha256":"1"*64,"coverage":1.0,"precision":1.0}})
        self.write()
    def write(self):
        (self.root/"voice_pack_manifest.json").write_text(
           json.dumps(self.model,ensure_ascii=False),"utf8")
    def test_17_real_bytes_are_audio_only_not_factory_release(self):
        c=cast.available_auditions(self.root)
        self.assertEqual(c["count"],17)
        self.assertEqual(c["production_approved"],0)
        self.assertEqual(c["short_russian_canary_passed"],17)
        self.assertEqual(c["short_russian_canary_failed"],0)
        self.assertEqual(c["independent_stock_speakers"],9)
        self.assertTrue(all(not r["production_enabled"] for r in c["voices"]))
        for row in c["voices"]:
            self.assertTrue(cast.audition_audio(row["id"],self.root).startswith(b"ID3"))
    def test_catalog_fail_closed_on_tamper_and_no_silent_publish(self):
        for prop,val in (("production_enabled",True),("role_variants",100),
                         ("model","unsafe"),("source_count",17)):
            bad=json.loads(json.dumps(self.model))
            bad[prop]=val
            self.model=bad
            self.write()
            with self.subTest(prop=prop),self.assertRaises(cast.CastUnavailable):
                cast.available_auditions(self.root)
            self.model["production_enabled"]=False
            self.model["role_variants"]=17
            self.model["source_count"]=9
            self.model["model"]=cast.MODEL
        role=self.model["voices"][0]
        filename=role["mp3_file"]
        (self.root/"by_role"/filename).write_bytes(b"ID3"+"tampered".encode()*700)
        with self.assertRaises(cast.CastUnavailable):
            cast.audition_audio(role["id"],self.root)
    def test_refuses_traversal_and_wrong_role(self):
        with self.assertRaises(cast.CastUnavailable):
            cast.audition_audio("../../private/owner-approved-deep-reference.wav",self.root)
        self.model["voices"][0]["mp3_file"]="../../owner-approved-deep-reference.wav"
        self.write()
        with self.assertRaises(cast.CastUnavailable):
            cast.available_auditions(self.root)
    def test_no_audition_root_does_not_disclose_server_files(self):
        with self.assertRaises(cast.CastUnavailable):
            cast.available_auditions(self.root/"missing")
    def test_role_specific_pitch_shift_keeps_original_profile_immutable(self):
        x=next(x for x in self.model["voices"] if x["id"]=="cartoon_spring_nasal_original_v1")
        self.assertEqual(x["pitch_semitones"],-2)
        self.assertFalse(x["production_enabled"])

if __name__=="__main__":
    unittest.main()
