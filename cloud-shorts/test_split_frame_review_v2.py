"""No-network regression on a third, real immutable Deep MP4 frame review.

Existing v1 denial is preserved, and v2 adds no way to publish an unreviewed
or replaced file. Model sees independent three-frame real MP4 chapters, not
coarse shared prompts / metadata.
"""
import base64
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import unittest

from autonomous_visual_review import (
    eligible_private_episode,select_private,verified_model_response,
    checked_review)
from split_frame_review_v2 import (
    EPISODE_ID,RENDER_RUN,MOVIE_SHA256,VOICE_SHA256,
    V1_REJECTION_PATH,V2_REJECTION_PATH,
    exact_assets,exact_receipt,eligible_rereview,review)
from visual_director import visual_asset_fingerprint

HERE=Path(__file__).resolve().parent


def git_fixture(obj):
    data=json.dumps(obj).encode("utf8")
    return {"sha":hashlib.sha1(b"blob "+str(len(data)).encode("ascii")+
                              b"\x00"+data).hexdigest(),
            "size":len(data),"encoding":"base64",
            "content":base64.b64encode(data).decode("ascii")}


def actual_like_frames():
    scenes=[]
    for source in ("clip_0","clip_1"):
        blobs=[b"\xff\xd8\xff"+(source+str(i)).encode("ascii")*650
               for i in range(3)]
        scenes.append({
            "source":source,"scene_action":"ride" if source=="clip_0" else "jump",
            "images":[base64.b64encode(b).decode("ascii") for b in blobs],
            "frames_sha256":[hashlib.sha256(b).hexdigest() for b in blobs]})
    return scenes


def scene_result(action,confidence):
    return {
        "action":action, "action_supported":True, "confidence":confidence,
        "observed":("Мотоцикл едет по дороге к камере на фоне зданий."
                    if action=="riding" else
                    "Мотоцикл с райдером полностью в воздухе над трассой."),
        "narration_scene_supported":True,
        "no_static_slide_majority":True,
        "no_embedded_channel_branding":True,
        "safe_for_release":True,
    }


class StrictSplitVisionForExistingMovie(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalog=json.loads((HERE/"episodes.json").read_text(encoding="utf8"))
        cls.episode=next(x for x in catalog["episodes"] if x["id"]==EPISODE_ID)

    def receipt(self):
        return {
            "id":EPISODE_ID,"state":"preview_ready",
            "run_id":RENDER_RUN,"attempt_count":3,
            "deep_source_sha256":VOICE_SHA256,
            "voice_qa_passed":True,"mixed_audio_qa_passed":True}

    def paths(self):
        return [
            "render-receipts/"+EPISODE_ID+".json",
            V1_REJECTION_PATH+"/"+EPISODE_ID+"-"+RENDER_RUN+".json"
        ]

    def test_new_protocol_exact_assets_and_old_decline_retained(self):
        self.assertTrue(exact_assets(self.episode,RENDER_RUN,MOVIE_SHA256))
        self.assertTrue(exact_receipt(self.episode,self.receipt()))
        self.assertTrue(eligible_rereview(
            self.episode,self.receipt(),self.paths()))
        self.assertFalse(eligible_rereview(
            self.episode,self.receipt(),
            self.paths()+[V2_REJECTION_PATH+"/"+EPISODE_ID+"-"+RENDER_RUN+".json"]))
        self.assertFalse(exact_assets(self.episode,"42482620427",MOVIE_SHA256))
        self.assertFalse(exact_assets(self.episode,RENDER_RUN,"0"*64))
        changed=deepcopy(self.episode)
        changed["deep_audio"]["source_audio_sha256"]="0"*64
        self.assertFalse(exact_assets(changed,RENDER_RUN,MOVIE_SHA256))
        changed=deepcopy(self.episode)
        changed["footage"][0]["native_4k_sha256"]="0"*64
        self.assertFalse(exact_assets(changed,RENDER_RUN,MOVIE_SHA256))
        self.assertFalse(eligible_rereview(
            self.episode,self.receipt(),[]))

    def test_immutable_old_rejection_permits_only_one_new_versioned_review(self):
        slug=EPISODE_ID
        wanted="daily-preview-"+slug+"-"+RENDER_RUN
        def fetch(path,method="GET",data=None):
            if path.startswith("contents/render-receipts/"):
                return git_fixture(self.receipt())
            if path.startswith("actions/runs/"):
                return {"total_count":1,
                        "artifacts":[{"name":wanted,"expired":False,
                                      "size_in_bytes":15978204}]}
            raise AssertionError(path)
        result=select_private({"episodes":[self.episode]},self.paths(),get=fetch)
        self.assertEqual(result,{"id":slug,"run_id":RENDER_RUN,
                                 "artifact_name":wanted})
        self.assertIsNone(select_private({"episodes":[self.episode]},
            self.paths()+[V2_REJECTION_PATH+"/"+slug+"-"+RENDER_RUN+".json"],
            get=fetch))
        self.assertIsNone(select_private({"episodes":[self.episode]},
            self.paths()+["publication-receipts/"+slug+".json"],get=fetch))

    def test_scene_by_scene_model_gets_exact_three_images_each_and_no_remote_key(self):
        chapters=actual_like_frames()
        expected=(scene_result("riding",.95),scene_result("stunt_jump",.98))
        called=[]
        def opener(request,timeout=None):
            body=json.loads(request.data)
            self.assertEqual(timeout,420)
            self.assertEqual(body["model"],"qwen3.5:4b")
            self.assertEqual(body["format"],"json")
            self.assertEqual(len(body["messages"]),2)
            self.assertEqual(len(body["messages"][1]["images"]),3)
            self.assertNotIn("Authorization",request.headers)
            idx=len(called)
            self.assertEqual(body["messages"][1]["images"],chapters[idx]["images"])
            self.assertIn("Оцени ТОЛЬКО",body["messages"][0]["content"])
            called.append(body)
            return io.BytesIO(json.dumps({"message":{
                "content":json.dumps(expected[idx],ensure_ascii=False)}},
                ensure_ascii=False).encode("utf8"))
        verdict=review(chapters,self.episode,"ollama","",
                       "http://127.0.0.1:11434/api/chat",
                       "qwen3.5:4b",opener=opener)
        self.assertEqual(len(called),2)
        self.assertTrue(verified_model_response(verdict,chapters))
        self.assertEqual([x["confidence"] for x in verdict["chapters"]],[.95,.98])
        self.assertTrue(verdict["independent_events_not_fabricated"])
        self.assertTrue(verdict["narration_fully_supported"])

    def test_ambiguous_action_spoof_or_unsafe_output_never_passes(self):
        original=actual_like_frames()
        for change in ("low_confidence","bad_action","safety_false",
                       "branding_false","slides_false","narration_false"):
            with self.subTest(change=change):
                rows=[scene_result("riding",.95),scene_result("stunt_jump",.98)]
                idx=0
                if change=="low_confidence":rows[0]["confidence"]=.91
                elif change=="bad_action":rows[0]["action"]="standing"
                elif change=="safety_false":rows[1]["safe_for_release"]=False
                elif change=="branding_false":rows[1]["no_embedded_channel_branding"]=False
                elif change=="slides_false":rows[1]["no_static_slide_majority"]=False
                elif change=="narration_false":rows[0]["narration_scene_supported"]=False
                def opener(request,timeout=None):
                    nonlocal idx
                    reply={"message":{"content":json.dumps(rows[idx],ensure_ascii=False)}}
                    idx+=1
                    return io.BytesIO(json.dumps(reply).encode("utf8"))
                out=review(original,self.episode,"ollama","",
                           "http://127.0.0.1:11434/api/chat","qwen3.5:4b",
                           opener=opener)
                self.assertFalse(verified_model_response(out,original))

    def test_forged_jpeg_or_untrusted_model_cannot_review(self):
        bad=actual_like_frames()
        bad[0]["frames_sha256"][1]="0"*64
        with self.assertRaisesRegex(RuntimeError,"FRAME_SHA"):
            review(bad,self.episode,"ollama","",
                   "http://127.0.0.1:11434/api/chat","qwen3.5:4b")
        with self.assertRaisesRegex(RuntimeError,"UNTRUSTED"):
            review(actual_like_frames(),self.episode,"ollama","",
                   "https://model.attacker.test/api/chat","qwen3.5:4b")

    def test_approved_proof_requires_v2_protocol_and_actual_exact_mp4_sha(self):
        ep=deepcopy(self.episode)
        ep["auto_publish"]=True
        ep["visual_revision_status"]="automated_frame_review_passed"
        ep["reviewed_mp4_sha256"]=MOVIE_SHA256
        ep["reviewed_artifact_run_id"]=RENDER_RUN
        proof={
            "version":1,"protocol_version":2,
            "status":"passed","episode_id":EPISODE_ID,
            "render_run_id":RENDER_RUN,"mp4_sha256":MOVIE_SHA256,
            "asset_fingerprint":visual_asset_fingerprint(ep),
            "model_provider":"ollama","model":"qwen3.5:4b",
            "no_embedded_channel_branding":True,
            "no_static_slide_majority":True,
            "chapters":[{
                "source":source,"visible_motorcycle":True,"action_supported":True,
                "confidence":confidence,"observed":"Мотоцикл и райдер в реальном действии",
                "frames_sha256":["b"*64,"c"*64,"d"*64]}
                for source,confidence in [("clip_0",.95),("clip_1",.98)]]
        }
        ep["automated_frame_review"]=proof
        self.assertTrue(checked_review(ep,MOVIE_SHA256))
        forged=deepcopy(ep)
        forged["automated_frame_review"]["protocol_version"]=1
        self.assertFalse(checked_review(forged,MOVIE_SHA256))
        forged=deepcopy(ep)
        forged["automated_frame_review"]["mp4_sha256"]="0"*64
        self.assertFalse(checked_review(forged,MOVIE_SHA256))


if __name__=="__main__":
    unittest.main()
