"""Owner's three explicitly chosen uploads, without replacing GUSTAVA DEEP."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import owner_voice_selection as module


class OwnerVoiceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.fake_proofs={}
        for role,proof in module.SAMPLE_PROOFS.items():
            d=dict(proof)
            payload=(b"RIFF" if role=="grandma" else b"ID3")+bytes([len(role)])*2500
            (self.root/d["filename"]).write_bytes(payload)
            d["sha256"]=hashlib.sha256(payload).hexdigest()
            self.fake_proofs[role]=d
        patcher=patch.object(module,"SAMPLE_PROOFS",self.fake_proofs)
        patcher.start(); self.addCleanup(patcher.stop)
        self.sel={"version":1,"owner_primary_deep_unchanged":True,
                  "production_approved_count":0,"rejected_other_original_cast_roles":True,
                  "selected_roles":list(self.fake_proofs),
                  "samples":[]}
        for role,proof in self.fake_proofs.items():
            self.sel["samples"].append({
                "role_id":role,"owner_audition_selected":True,
                "production_enabled":False,
                "can_use_as_default_gustava_narrator":False,
                "reference_sha256":proof["sha256"],
                "source_speaker":proof["source_speaker"],
                "pitch_semitones":proof["pitch_semitones"],
                "reference_file":str(self.root/proof["filename"])
            })
        self.save()

    def save(self):
        (self.root/"selection.json").write_text(
            json.dumps(self.sel,ensure_ascii=False),"utf8")

    def test_only_three_user_selected_real_assets_available(self):
        data=module.owner_voice_list(self.root)
        self.assertEqual(data["selected_count"],3)
        self.assertEqual(data["original_cartoon_candidates"],0)
        self.assertEqual(data["production_approved_count"],0)
        self.assertTrue(data["original_deep_unchanged"])
        self.assertTrue(data["rejected_other_legacy_cast"])
        self.assertEqual({x["id"] for x in data["voices"]},
                         {"mother","grandma","warm_biker_woman"})
        for x in data["voices"]:
            payload,mime,filename=module.owner_voice_bytes(x["id"],self.root)
            self.assertGreater(len(payload),1000)
            self.assertEqual(filename,x["download_filename"])
            self.assertEqual(mime,x["mime_type"])
            self.assertFalse(x["production_enabled"])
        self.assertFalse(next(x for x in data["voices"] if x["id"]=="grandma")
                         ["audition_short_asr_passed"])

    def test_rejected_other_candidates_never_available(self):
        for bad in ["cartoon_spring_nasal_original_v1","father","son_teen","../owner-tts.env"]:
            with self.subTest(role=bad), self.assertRaises(module.SelectionUnavailable):
                module.owner_voice_bytes(bad,self.root)
        self.assertEqual(module.owner_voice_list(self.root)["selected_count"],3)

    def test_corrupted_or_replaced_selected_file_denied(self):
        (self.root/"07_mother.mp3").write_bytes(b"ID3"+b"forged"*1500)
        with self.assertRaises(module.SelectionUnavailable):
            module.owner_voice_list(self.root)
        with self.assertRaises(module.SelectionUnavailable):
            module.owner_voice_bytes("mother",self.root)

    def test_fake_production_approval_refused(self):
        self.sel["production_approved_count"]=3;self.save()
        with self.assertRaises(module.SelectionUnavailable):
            module.owner_voice_list(self.root)
        self.sel["production_approved_count"]=0
        self.sel["owner_primary_deep_unchanged"]=False;self.save()
        with self.assertRaises(module.SelectionUnavailable):
            module.owner_voice_list(self.root)

    def test_original_cartoon_candidate_has_provenance_but_no_release(self):
        wav=b"ID3"+bytes(2600)
        fn="CARTOON_VOICEDESIGN_V2_A.mp3"
        (self.root/fn).write_bytes(wav)
        experimental={
          "model":"Qwen3-TTS-12Hz-1.7B-VoiceDesign",
          "public_release_approved":False,
          "imitates_existing_character":False,
          "candidates":[{
              "id":"cartoon_bubbly_v2_a","filename":fn,
              "sha256":hashlib.sha256(wav).hexdigest(),
              "model":"Qwen3-TTS-12Hz-1.7B-VoiceDesign",
              "production_enabled":False,"asr_short_canary_passed":True,
              "pitch_semitones":-2,"duration_seconds":12.0,
              "name_ru":"Оригинальный мультяшный"
          }]
        }
        path=self.root/"cartoon_voice_design_manifest.json"
        path.write_text(json.dumps(experimental),"utf8")
        voices=module.owner_voice_list(self.root)
        self.assertEqual(voices["original_cartoon_candidates"],1)
        self.assertEqual(len(voices["voices"]),4)
        data,mime,_=module.owner_voice_bytes("cartoon_bubbly_v2_a",self.root)
        self.assertEqual(data,wav)
        self.assertEqual(mime,"audio/mpeg")
        experimental["candidates"][0]["production_enabled"]=True
        path.write_text(json.dumps(experimental),"utf8")
        with self.assertRaises(module.SelectionUnavailable):
            module.owner_voice_list(self.root)
        experimental["candidates"][0]["production_enabled"]=False
        experimental["candidates"][0]["filename"]="../../secret.mp3"
        path.write_text(json.dumps(experimental),"utf8")
        with self.assertRaises(module.SelectionUnavailable):
            module.owner_voice_list(self.root)

if __name__=="__main__":
    unittest.main()
