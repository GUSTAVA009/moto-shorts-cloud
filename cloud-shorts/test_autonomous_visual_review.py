import base64
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import autonomous_visual_review as review
from selfhosted_voice import CARTOON_B_PROFILE_ID
from visual_director import visual_asset_fingerprint


class AutonomousFactoryVisualReviewTests(unittest.TestCase):
    def make_episode(self):
        return {
            "id":"moto-autoreview-test-001",
            "auto_preview":True,"auto_publish":False,
            "editorial_format":"source_anchored_action_contrast",
            "visual_director_version":3,
            "voice_engine":"gustava_selfhosted_qwen3",
            "voice_profile":CARTOON_B_PROFILE_ID,
            "selfhosted_voice_id":"gustava-cartoon-b-v1",
            "narration":"Мотоцикл в разных кадрах: первый райдер едет по трассе. "
                        "На втором видео мотоциклист прыгает с трамплина. "
                        "Это разные съёмки. Что тебе ближе?",
            "title":"Поездка и прыжок #shorts",
            "footage":[
                {"key":"clip_0","author":"Tom Fisk","license":"Pexels License",
                 "url":"https://www.pexels.com/download/video/9132992/",
                 "source_page":"https://www.pexels.com/video/people-riding-motocross-9132992/"},
                {"key":"clip_1","author":"Michael Novogradac","license":"Pexels License",
                 "url":"https://www.pexels.com/download/video/15298841/",
                 "source_page":"https://www.pexels.com/video/motocross-biker-makes-some-jumps-15298841/"},
            ],
            "shots":[{"source":"clip_0","start":0,"seconds":7},
                     {"source":"clip_1","start":0,"seconds":7}],
        }

    def make_receipt(self):
        return {"id":"moto-autoreview-test-001","state":"preview_ready",
                "selfhosted_voice_id":"gustava-cartoon-b-v1",
                "voice_qa_passed":True,"mixed_audio_qa_passed":True,
                "run_id":"41438910472"}

    def make_proof(self, ep):
        return {"version":1,"status":"passed",
                "episode_id":ep["id"],"render_run_id":"41438910472",
                "mp4_sha256":"a"*64,
                "asset_fingerprint":visual_asset_fingerprint(ep),
                "model_provider":"openai","model":"gpt-4.1-mini",
                "chapters":[{"source":f["key"],"visible_motorcycle":True,
                             "action_supported":True,"confidence":0.99,
                             "observed":"Actual motorcycle action in real scene",
                             "frames_sha256":["b"*64,"c"*64,"d"*64]}
                            for f in ep["footage"]]}

    def test_runner_vision_can_work_without_paid_provider_keys(self):
        env = {"GUSTAVA_LOCAL_VISION_ENABLED":"1", "OPENAI_API_KEY":"",
               "OPENROUTER_API_KEY":""}
        with patch.dict(os.environ, env, clear=True):
            provider, secret, url, model = review.model_credentials()
        self.assertEqual(provider, "ollama")
        self.assertEqual(secret, "")
        self.assertEqual(url, "http://127.0.0.1:11434/api/chat")
        self.assertEqual(model, "qwen3.5:4b")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError,
                                        "AUTO_FRAME_REVIEW_PROVIDER_KEY_MISSING"):
                review.model_credentials()

    def test_ollama_request_inspects_both_real_frame_chapters_and_no_remote_token(self):
        images = [base64.b64encode(b"\\xff\\xd8\\xff"+bytes([i])*3000).decode("ascii")
                  for i in range(6)]
        chapters = [
            {"source":"clip_0","expected":"райдер едет по трассе",
             "images":images[:3]},
            {"source":"clip_1","expected":"райдер прыгает с трамплина",
             "images":images[3:]},
        ]
        strong = {"chapters":[
                     {"visible_motorcycle":True,"action_supported":True,
                      "confidence":0.98,"observed":"Two actual riders on a dirt road"},
                     {"visible_motorcycle":True,"action_supported":True,
                      "confidence":0.95,"observed":"Rider seen airborne over the jump"}],
                  "narration_fully_supported":True,
                  "independent_events_not_fabricated":True,
                  "safe_for_release":True}
        sent=[]
        def fake_urlopen(request, timeout=0):
            sent.append((request,timeout))
            body=json.loads(request.data.decode("utf8"))
            self.assertEqual(body["model"],"qwen3.5:4b")
            self.assertEqual(body["format"],"json")
            self.assertFalse(body["stream"])
            self.assertFalse(body["think"])
            self.assertEqual(len(body["messages"]),5)
            self.assertEqual(body["messages"][2]["images"],images[:3])
            self.assertEqual(body["messages"][3]["images"],images[3:])
            return io.BytesIO(json.dumps(
                {"message":{"content":json.dumps(strong)}}).encode("utf8"))
        with patch.object(review.urllib.request, "urlopen", side_effect=fake_urlopen):
            output = review.request_vision(
                chapters,self.make_episode(),"ollama","",
                "http://127.0.0.1:11434/api/chat","qwen3.5:4b")
        self.assertEqual(output,strong)
        self.assertTrue(review.verified_model_response(output,chapters))
        self.assertEqual(len(sent),1)
        self.assertGreaterEqual(sent[0][1],300)
        self.assertNotIn("Authorization",sent[0][0].headers)
        with self.assertRaisesRegex(RuntimeError,"UNTRUSTED_OLLAMA_ENDPOINT"):
            review.request_vision(chapters,self.make_episode(),"ollama","",
                                  "https://untrusted.test/api/chat","qwen3.5:4b")

    def test_local_visual_model_uncertain_answer_cannot_approve(self):
        chapters=[{"source":"clip_0"},{"source":"clip_1"}]
        weak={"chapters":[
                {"visible_motorcycle":True,"action_supported":False,
                 "confidence":0.99,"observed":"Bike is static; rider not moving"},
                {"visible_motorcycle":True,"action_supported":True,
                 "confidence":0.98,"observed":"A jump is clearly visible"}],
              "narration_fully_supported":True,
              "independent_events_not_fabricated":True,
              "safe_for_release":True}
        self.assertFalse(review.verified_model_response(weak,chapters))

    def test_only_genuine_private_cartoon_b_with_two_distinct_actions(self):
        ep=self.make_episode()
        receipt=self.make_receipt()
        self.assertTrue(review.eligible_private_episode(ep,receipt))
        self.assertFalse(review.eligible_private_episode(
            dict(ep,auto_publish=True),receipt))
        self.assertFalse(review.eligible_private_episode(
            dict(ep,editorial_format="some_unverified_template"),receipt))
        self.assertFalse(review.eligible_private_episode(
            dict(ep,visual_review_failed=True),receipt))
        self.assertFalse(review.eligible_private_episode(
            dict(ep,selfhosted_voice_id="gustava-original-v1"),receipt))
        self.assertFalse(review.eligible_private_episode(
            ep,dict(receipt,mixed_audio_qa_passed=False)))
        repeated=deepcopy(ep)
        repeated["footage"][1]["author"]=repeated["footage"][0]["author"]
        self.assertFalse(review.eligible_private_episode(repeated,receipt))

    def test_verified_external_evidence_never_impersonates_assistant(self):
        ep=self.make_episode()
        proof=self.make_proof(ep)
        ep.update({"auto_publish":True,
                   "visual_revision_status":"automated_frame_review_passed",
                   "automated_frame_review":proof,
                   "reviewed_mp4_sha256":proof["mp4_sha256"],
                   "reviewed_artifact_run_id":proof["render_run_id"]})
        self.assertTrue(review.checked_review(ep,proof["mp4_sha256"]))
        self.assertFalse(review.checked_review(ep,"f"*64))
        self.assertFalse(review.checked_review(dict(ep,auto_publish=False)))
        self.assertFalse(review.checked_review(
            dict(ep,visual_revision_status="assistant_checked_passed")))
        self.assertFalse(review.checked_review(dict(ep,
            automated_frame_review=dict(proof,model_provider="fake"))))
        tampered=deepcopy(ep)
        tampered["footage"][0]["source_page"]="https://www.pexels.com/video/fake-9132992/"
        self.assertFalse(review.checked_review(tampered))
        weak=deepcopy(ep)
        weak["automated_frame_review"]["chapters"][0]["confidence"]=0.1
        self.assertFalse(review.checked_review(weak))

    def test_unknown_or_uncertain_real_frame_action_stays_private(self):
        chapters=[{"source":"clip_0"},{"source":"clip_1"}]
        strong={"chapters":[{"visible_motorcycle":True,"action_supported":True,
                             "confidence":0.98,"observed":"Visible riding action"},
                            {"visible_motorcycle":True,"action_supported":True,
                             "confidence":0.96,"observed":"Rider airborne mid-jump"}],
                "narration_fully_supported":True,
                "independent_events_not_fabricated":True,
                "safe_for_release":True}
        self.assertTrue(review.verified_model_response(strong,chapters))
        not_riding=deepcopy(strong)
        not_riding["chapters"][0]["action_supported"]=False
        self.assertFalse(review.verified_model_response(not_riding,chapters))
        weak=deepcopy(strong)
        weak["chapters"][1]["confidence"]=0.92
        self.assertFalse(review.verified_model_response(weak,chapters))
        fabricated=deepcopy(strong)
        fabricated["independent_events_not_fabricated"]=False
        self.assertFalse(review.verified_model_response(fabricated,chapters))
        missing=deepcopy(strong)
        missing["chapters"].pop()
        self.assertFalse(review.verified_model_response(missing,chapters))

    def test_auto_review_progresses_after_rejection_without_manual_video_release(self):
        episode=self.make_episode()
        receipt=self.make_receipt()
        slug=episode["id"]
        run_id=receipt["run_id"]
        ledger_paths=["render-receipts/"+slug+".json",
                      review.REVIEW_REJECTION_PATH+"/prior-rejected-999.json"]
        calls=[]
        def fake_api(path,method="GET",data=None):
            calls.append((method,path,data))
            if path=="git/trees/render-ledger?recursive=1":
                return {"truncated":False,
                        "tree":[{"type":"blob","path":p} for p in ledger_paths]}
            if path=="contents/cloud-shorts/episodes.json?ref=main":
                return {"sha":"sha","content":base64.b64encode(
                    json.dumps({"episodes":[episode]}).encode()).decode()}
            if path.startswith("contents/render-receipts/"):
                return {"sha":"sha","content":base64.b64encode(
                    json.dumps(receipt).encode()).decode()}
            if path.startswith("actions/runs/"):
                return {"total_count":1,"artifacts":[{"expired":False,
                    "name":"daily-preview-"+slug+"-"+run_id,
                    "size_in_bytes":7000000}]}
            if path=="actions/workflows/autonomous-editorial-review.yml/dispatches":
                self.assertEqual(method,"POST")
                self.assertEqual(data,{"ref":"main"})
                return {}
            raise AssertionError(path)
        self.assertTrue(review.dispatch_next_unreviewed_original(
            "prior-rejected",get=fake_api))
        self.assertEqual(len([v for v in calls if v[0]=="POST"]),1)
        calls.clear()
        self.assertFalse(review.dispatch_next_unreviewed_original(
            slug,get=fake_api))
        self.assertFalse(any(v[0]=="POST" for v in calls))
        ledger_paths.append(review.REVIEW_REJECTION_PATH+"/"+slug+"-"+run_id+".json")
        calls.clear()
        self.assertFalse(review.dispatch_next_unreviewed_original(
            "prior-rejected",get=fake_api))
        self.assertFalse(any(v[0]=="POST" for v in calls))

    def test_private_selection_requires_real_unexpired_artifact_and_no_post_receipt(self):
        ep=self.make_episode()
        receipt=self.make_receipt()
        encoded=base64.b64encode(json.dumps(receipt).encode()).decode()
        slug=ep["id"]
        name="daily-preview-"+slug+"-41438910472"
        def fetch(path,method="GET",data=None):
            if path.startswith("contents/render-receipts/"):
                return {"sha":"abc","content":encoded}
            if path.startswith("actions/runs/"):
                return {"total_count":1,"artifacts":[{
                    "id":111,"expired":False,"name":name,"size_in_bytes":3000000}]}
            raise AssertionError(path)
        paths=["render-receipts/"+slug+".json"]
        chosen=review.select_private({"episodes":[ep]},paths,get=fetch)
        self.assertEqual(chosen,{"id":slug,"run_id":"41438910472",
                                 "artifact_name":name})
        self.assertIsNone(review.select_private({"episodes":[ep]},
            paths+["buffer-publication-receipts/"+slug+".json"],get=fetch))
        self.assertIsNone(review.select_private({"episodes":[ep]},
            paths+[review.REVIEW_REJECTION_PATH+"/"+slug+"-41438910472.json"],
            get=fetch))

    def test_actual_mp4_frames_are_sampled_from_both_nonrepeated_scenes(self):
        ep=self.make_episode()
        visual={"version":3,"passed":True,"episode":ep["id"],
                "source_sequence":["clip_0","clip_1"],
                "source_reused_in_short":False,"caption_fit_passed":True,
                "sequence":[{"source":"clip_0","seconds":6.2},
                            {"source":"clip_1","seconds":6.1}]}
        encoded=b"\xff\xd8\xff"+b"actual-jpeg-test"*300
        with patch.object(review.subprocess,"run",
                          return_value=SimpleNamespace(stdout=encoded)) as mocked:
            frames=review.actual_frames(Path("/fake/real-mp4.mp4"),visual,ep)
        self.assertEqual(mocked.call_count,6)
        self.assertEqual([x["source"] for x in frames],["clip_0","clip_1"])
        self.assertEqual(len(frames[0]["frames_sha256"]),3)
        self.assertEqual(frames[1]["frames_sha256"][0],
                         hashlib.sha256(encoded).hexdigest())
        broken=dict(visual,source_sequence=["clip_1","clip_0"])
        with self.assertRaisesRegex(ValueError,"FINAL_VISUAL_QA_MISMATCH"):
            review.actual_frames(Path("/fake.mp4"),broken,ep)


if __name__ == "__main__":
    unittest.main()
