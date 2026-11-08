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

def git_fixture(obj):
    """Make a faithful Contents API object, not an impossible sha placeholder."""
    raw=json.dumps(obj).encode("utf8")
    digest=hashlib.sha1(b"blob "+str(len(raw)).encode("ascii")+b"\x00"+raw).hexdigest()
    return {"sha":digest,"size":len(raw),"encoding":"base64",
            "content":base64.b64encode(raw).decode("ascii")}


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
                "no_embedded_channel_branding":True,
                "no_static_slide_majority":True,
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
                  "safe_for_release":True,
                  "no_embedded_channel_branding":True,
                  "no_static_slide_majority":True}
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
              "safe_for_release":True,
                  "no_embedded_channel_branding":True,
                  "no_static_slide_majority":True}
        self.assertFalse(review.verified_model_response(weak,chapters))

    def test_owner_rejected_brand_and_static_slide_majority_fail_closed(self):
        chapters=[{"source":"clip_0"},{"source":"clip_1"}]
        strong={"chapters":[
                {"visible_motorcycle":True,"action_supported":True,
                 "confidence":0.98,"observed":"Rider visibly moving through a forest"},
                {"visible_motorcycle":True,"action_supported":True,
                 "confidence":0.97,"observed":"Motocross motorcycle jumping on a prepared track"}],
            "narration_fully_supported":True,
            "independent_events_not_fabricated":True,
            "safe_for_release":True,
            "no_embedded_channel_branding":True,
            "no_static_slide_majority":True}
        self.assertTrue(review.verified_model_response(strong,chapters))
        for field in ("no_embedded_channel_branding","no_static_slide_majority"):
            altered=dict(strong,**{field:False})
            self.assertFalse(review.verified_model_response(altered,chapters))
            altered=dict(strong)
            del altered[field]
            self.assertFalse(review.verified_model_response(altered,chapters))

    def test_original_educational_microguide_is_eligible_for_independent_frames(self):
        ep=self.make_episode()
        ep["editorial_format"]="original_action_microguide_v1"
        self.assertTrue(review.eligible_private_episode(ep,self.make_receipt()))

    def test_three_actual_native_2k_deep_shorts_can_enter_strict_frame_review(self):
        # Regression: the factory rendered these actual MP4s, but the
        # old two-format allowlist silently stranded them before ANY frames
        # were inspected. This only allows candidacy, NOT public upload.
        records = {
            "moto-city-9561eabb9e24": "42354543323",
            "moto-roadtrip-83f0461a1801": "42354718553",
            "moto-helmet-3368471b0f59": "42354884536",
        }
        actual = {e["id"]: e for e in json.loads(
            (Path(__file__).parent / "episodes.json").read_text(encoding="utf8")
        )["episodes"] if e["id"] in records}
        self.assertEqual(set(actual),set(records))
        for slug, run_id in records.items():
            ep = actual[slug]
            receipt = {"id":slug, "state":"preview_ready",
                       "run_id":run_id,
                       "deep_source_sha256":ep["deep_audio"]["source_audio_sha256"],
                       "voice_qa_passed":True,
                       "mixed_audio_qa_passed":True}
            with self.subTest(slug=slug):
                self.assertTrue(review.eligible_private_episode(ep,receipt))
                self.assertFalse(review.eligible_private_episode(
                    dict(ep,auto_publish=True),receipt))
                self.assertFalse(review.eligible_private_episode(
                    dict(ep,editorial_format="owner_rejected_static_slides"),
                    receipt))
                self.assertFalse(review.eligible_private_episode(
                    dict(ep,visual_review_failed=True),receipt))
                self.assertFalse(review.eligible_private_episode(
                    ep,dict(receipt,deep_source_sha256="0"*64)))

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

    def test_verified_real_deep_4k_mp4_enters_independent_review_not_voice_bypass(self):
        from pathlib import Path
        approved=next(x for x in json.loads(
            (Path(__file__).parent/"episodes.json").read_text(encoding="utf8"))["episodes"]
            if x["id"]=="moto-native-4k-control-20261106")
        voice_sha=approved["deep_audio"]["source_audio_sha256"]
        receipt={"id":approved["id"],"state":"preview_ready",
                 "run_id":"42273013206","deep_source_sha256":voice_sha,
                 "voice_qa_passed":True,"mixed_audio_qa_passed":True}
        self.assertTrue(review.has_approved_original_deep(approved))
        self.assertTrue(review.eligible_private_episode(approved,receipt))
        self.assertFalse(review.eligible_private_episode(
            approved,dict(receipt,deep_source_sha256="0"*64)))
        self.assertFalse(review.eligible_private_episode(
            approved,dict(receipt,voice_qa_passed=False)))
        self.assertFalse(review.eligible_private_episode(
            approved,dict(receipt,mixed_audio_qa_passed=False)))
        self.assertFalse(review.eligible_private_episode(
            dict(approved,auto_publish=True),receipt))
        self.assertFalse(review.eligible_private_episode(
            dict(approved,voice_profile="unapproved"),receipt))
        self.assertFalse(review.eligible_private_episode(
            dict(approved,voice_engine="unapproved"),receipt))
        self.assertFalse(review.eligible_private_episode(
            dict(approved,visual_review_failed=True),receipt))

    def test_same_owner_two_different_ltx_original_shots_are_reviewable(self):
        ep = self.make_episode()
        r = self.make_receipt()
        base = "https://84-252-66-87.sslip.io/yt-factory-originals"
        batch = "20261103034102-aabbcc"
        originals=[]
        for i,(sha,action) in enumerate((("a"*64,"riding"),("b"*64,"jump"))):
            originals.append({
                "key":"clip_"+str(i),
                "author":"GUSTAVA Original Video Production",
                "license":"LTX OpenRAIL-M",
                "generation_model":"ltxv-2b-0.9.8-distilled-fp8",
                "generation_batch":batch,
                "scene_action":action,
                "original_sha256":sha,
                "file_size":1500000,
                "duration":6.706,
                "url":base+"/clips/"+sha+".mp4",
                "source_page":base+"/meta/"+sha+".json",
            })
        ep["footage"]=originals
        self.assertTrue(review.eligible_private_episode(ep,r))
        for change in (
            {"original_sha256":"a"*64},    # duplicated source SHA
            # Different owner-original jobs are now allowed: retaining
            # this old restriction stranded legally owned clips.
            {"scene_action":"riding"},      # repeated action
            {"license":"Pexels License"},   # untruthful rights claim
        ):
            broken=deepcopy(ep)
            broken["footage"][1].update(change)
            self.assertFalse(review.eligible_private_episode(broken,r))
        different_batch=deepcopy(ep)
        different_batch["footage"][1]["generation_batch"]="20261103034202-ffaaaa"
        self.assertTrue(review.eligible_private_episode(different_batch,r))
        fake=deepcopy(ep)
        fake["footage"][1]["source_page"]="https://external.test/forged.mp4"
        self.assertFalse(review.eligible_private_episode(fake,r))

    def test_real_qwen_colon_model_name_can_pass_SHA_bound_visual_proof(self):
        ep=self.make_episode()
        proof=self.make_proof(ep)
        proof["model_provider"]="ollama"
        proof["model"]="qwen3.5:4b"
        ep.update({"auto_publish":True,
                   "visual_revision_status":"automated_frame_review_passed",
                   "automated_frame_review":proof,
                   "reviewed_mp4_sha256":proof["mp4_sha256"],
                   "reviewed_artifact_run_id":proof["render_run_id"]})
        self.assertTrue(review.checked_review(ep,proof["mp4_sha256"]))
        for fake in ("qwen3.5:other", "qwen3.5:4b;rm", "custom:external"):
            broken=deepcopy(ep)
            broken["automated_frame_review"]["model"]=fake
            self.assertFalse(review.checked_review(broken,proof["mp4_sha256"]))
        wrong=deepcopy(ep)
        wrong["automated_frame_review"]["model_provider"]="openai"
        self.assertFalse(review.checked_review(wrong,proof["mp4_sha256"]))
        self.assertFalse(review.checked_review(ep,"f"*64))

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
                "safe_for_release":True,
                  "no_embedded_channel_branding":True,
                  "no_static_slide_majority":True}
        self.assertTrue(review.verified_model_response(strong,chapters))
        not_riding=deepcopy(strong)
        not_riding["chapters"][0]["action_supported"]=False
        self.assertFalse(review.verified_model_response(not_riding,chapters))
        weak=deepcopy(strong)
        weak["chapters"][1]["confidence"]=0.91
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
                return git_fixture({"episodes":[episode]})
            if path.startswith("contents/render-receipts/"):
                return git_fixture(receipt)
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

    def test_actual_revised_motocross_mp4_can_reenter_six_frame_review(self):
        """Only new immutable render can be reviewed after first-shot rejection."""
        from pathlib import Path
        from copy import deepcopy
        full = json.loads((Path(__file__).parent/"episodes.json").read_text(
            encoding="utf8"))
        ep = next(x for x in full["episodes"]
                  if x["id"]=="moto-roadtrip-153fe6130270")
        original = {
            "id":ep["id"],"state":"preview_ready",
            "run_id":"42499999999","attempt_count":3,
            "deep_source_sha256":ep["deep_audio"]["source_audio_sha256"],
            "voice_qa_passed":True,"mixed_audio_qa_passed":True,
        }
        self.assertTrue(review.verified_unpublished_visual_revision(ep,original))
        self.assertTrue(review.eligible_private_episode(ep,original))
        self.assertFalse(review.eligible_private_episode(
            ep,dict(original,run_id="42400239823",attempt_count=1)))
        self.assertFalse(review.eligible_private_episode(
            ep,dict(original,run_id="42405242545",attempt_count=2)))
        self.assertFalse(review.eligible_private_episode(
            ep,dict(original,deep_source_sha256="0"*64)))
        self.assertFalse(review.eligible_private_episode(
            dict(ep,visual_review_failed=True),original))
        self.assertFalse(review.eligible_private_episode(
            dict(ep,auto_publish=True),original))
        tampered=deepcopy(ep)
        tampered["visual_revision_evidence"]["replacement_source_sha256"]="0"*64
        self.assertFalse(review.eligible_private_episode(tampered,original))
        tampered=deepcopy(ep)
        tampered["visual_revision_evidence"]["unchanged_second_source_id"]="wrong"
        self.assertFalse(review.eligible_private_episode(tampered,original))
        tampered=deepcopy(ep)
        tampered["visual_revision_requested"]=False
        tampered["visual_revision_status"]="needs_new_verified_visuals"
        self.assertFalse(review.eligible_private_episode(tampered,original))

    def test_private_selection_requires_real_unexpired_artifact_and_no_post_receipt(self):
        ep=self.make_episode()
        receipt=self.make_receipt()

        slug=ep["id"]
        name="daily-preview-"+slug+"-41438910472"
        def fetch(path,method="GET",data=None):
            if path.startswith("contents/render-receipts/"):
                return git_fixture(receipt)
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

    def test_large_1mb_catalog_resolves_exact_git_blob_with_sha_and_size(self):
        payload=json.dumps({"episodes":[],"pad":"x"*1100000}).encode("utf8")
        digest=hashlib.sha1(b"blob "+str(len(payload)).encode("ascii")+
                            b"\x00"+payload).hexdigest()
        entry={"sha":digest,"encoding":"none","size":len(payload),"content":""}
        blob={"sha":digest,"encoding":"base64","size":len(payload),
              "content":base64.b64encode(payload).decode("ascii")}
        with patch.object(review,"api",return_value=blob) as mocked:
            self.assertEqual(review.decode_file(entry)["episodes"],[])
            mocked.assert_called_once_with("git/blobs/"+digest)
        with patch.object(review,"api",return_value=dict(blob,size=len(payload)+1)):
            with self.assertRaisesRegex(RuntimeError,"BLOB_MISMATCH"):
                review.decode_file(entry)
        tampered=bytearray(payload)
        tampered[-1]=ord("y")
        bad_blob=dict(blob,content=base64.b64encode(tampered).decode("ascii"))
        with patch.object(review,"api",return_value=bad_blob):
            with self.assertRaisesRegex(RuntimeError,"GIT_CONTENT_SHA_MISMATCH"):
                review.decode_file(entry)
        with patch.object(review,"api") as mocked:
            with self.assertRaisesRegex(RuntimeError,"CORRUPT_OR_MISSING"):
                review.decode_file(dict(entry,size=700000))
            mocked.assert_not_called()

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
