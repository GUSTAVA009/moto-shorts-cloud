"""Exact owner-approved Cartoon B reference: tampering, OIDC, cache separation."""
import array
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import owner_clone_service as api


def wav():
    out=io.BytesIO()
    with wave.open(out,"wb") as x:
        x.setnchannels(1);x.setsampwidth(2);x.setframerate(24000)
        x.writeframes(array.array("h",[2700,-2600]*48000).tobytes())
    return out.getvalue()


class SelectedCartoonBEndpointTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        self.root=root
        folder=root/"private/owner_selected_20261102"
        folder.mkdir(parents=True)
        (root/"engine/qwen3-tts-0.6b-base").mkdir(parents=True)
        (root/"engine/qwen_tts").write_bytes(b"engine-fixture")
        (root/"private/owner-approved-deep-reference.wav").write_bytes(wav())
        (folder/"CARTOON_TAKE2_B_MINUS2.wav").write_bytes(wav())
        self.digest=hashlib.sha256(wav()).hexdigest()
        obj={
            "model":"Qwen3-TTS-12Hz-1.7B-VoiceDesign",
            "imitates_existing_character":False,
            "candidates":[{
                "id":"cartoon_original_voicedesign_v2_b",
                "wav_file":"CARTOON_TAKE2_B_MINUS2.wav",
                "sha256_wav":self.digest,
                "asr_short_canary_passed":True,
                "pitch_semitones":-2
            }]
        }
        self.manifest=folder/"cartoon_voice_design_manifest.json"
        self.manifest.write_text(json.dumps(obj),encoding="utf8")
        p=patch.dict(os.environ,{
            "OWNER_TTS_ROOT":str(root),
            "GUSTAVA_VOICE_REFERENCE_SHA256":hashlib.sha256(wav()).hexdigest(),
        })
        p.start()
        self.addCleanup(p.stop)
        q=patch.object(api,"CARTOON_B_REFERENCE_SHA",self.digest)
        q.start();self.addCleanup(q.stop)
        self.request={"text":"Привет, мы выезжаем на трек и проверяем тормоза!",
                      "voice":api.CARTOON_B_VOICE_ID,
                      "channel_slug":"gustava","response_format":"wav"}

    def test_B_has_distinct_reference_and_original_DEEP_kept(self):
        self.assertEqual(api.voice_paths(api.CARTOON_B_VOICE_ID)[-1],self.digest)
        self.assertEqual(api.voice_paths(api.VOICE_ID)[-1],self.digest)
        self.assertNotEqual(api.CARTOON_B_VOICE_ID,api.VOICE_ID)
        self.assertEqual(api.backend_label(api.CARTOON_B_VOICE_ID),
                         "qwen3_0.6b_base_cartoon_b_reference")
        self.assertEqual(api.validate_request(self.request,"cartoon-b-0001"),
                         self.request["text"])
        with self.assertRaises(PermissionError):
            api.validate_request(dict(self.request,voice="other"),"cartoon-b-0002")

    def test_changed_wav_manifest_or_alias_fail_closed(self):
        folder=self.root/"private/owner_selected_20261102"
        target=folder/"CARTOON_TAKE2_B_MINUS2.wav"
        with patch.object(api,"CARTOON_B_REFERENCE_SHA","f"*64):
            with self.assertRaisesRegex(RuntimeError,"SHA_MISMATCH"):
                api.cartoon_b_paths()
        self.manifest.write_text(json.dumps({
            "model":"Qwen3-TTS-12Hz-1.7B-VoiceDesign",
            "imitates_existing_character":False,"candidates":[]
        }),encoding="utf8")
        with self.assertRaisesRegex(RuntimeError,"PROVENANCE"):
            api.cartoon_b_paths()
        target.unlink()

    def test_same_request_id_cannot_swap_old_voice_to_B(self):
        called=[]
        def producer(text,target,*args):
            called.append(text)
            return wav()
        first, ref=api.build_audio(self.request,"cartoon-b-0005",producer=producer)
        self.assertEqual(ref,self.digest)
        self.assertEqual(first,wav())
        self.assertEqual(api.build_audio(self.request,"cartoon-b-0005",producer=producer)[0],wav())
        with self.assertRaisesRegex(ValueError,"IDEMPOTENCY_COLLISION"):
            api.build_audio(dict(self.request,voice=api.VOICE_ID),
                            "cartoon-b-0005",producer=producer)
        self.assertEqual(len(called),1)

if __name__=="__main__":
    unittest.main()
