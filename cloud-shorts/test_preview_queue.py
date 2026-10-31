"""Cloud preview queue pure/offline behavior tests."""
import unittest
import preview_queue as pq


class TestPreviewQueue(unittest.TestCase):
    def test_only_explicitly_approved_unused_episodes(self):
        episodes = [
            {"id": "first", "auto_preview": False},
            {"id": "second", "auto_preview": True},
            {"id": "third", "auto_preview": True},
        ]
        self.assertEqual(pq.pick(episodes, lambda i: i == "third"), "second")
        self.assertEqual(pq.pick(episodes, lambda i: i in {"second", "third"}), None)
        self.assertEqual(pq.pick(episodes, lambda i: False), "second")

    def test_exhausted_queue_returns_none(self):
        self.assertIsNone(pq.pick([], lambda _: False))
        self.assertIsNone(pq.pick([{"id": "draft"}], lambda _: False))

    def test_permanent_footage_history_rejects_reused_ids(self):
        import json
        from pathlib import Path
        catalog = json.loads((Path(__file__).parent / "episodes.json").read_text(encoding="utf8"))
        scene = catalog["episodes"][-1]
        first_source = scene["footage"][0]
        from editorial_guard import source_id
        old_id = source_id(first_source)
        history = {"version": 1, "used": {old_id: {"episode": "earlier-video"}}}
        with self.assertRaisesRegex(RuntimeError, "PERMANENT_SOURCE_REUSE_BLOCKED"):
            pq.assert_new_sources(scene, history)
        history["used"][old_id]["episode"] = scene["id"]
        pq.assert_new_sources(scene, history)

    def test_revised_unpublished_audio_may_retry_but_only_three_attempts(self):
        episode = {"id": "motorcycle-serial-01", "auto_preview": True}
        bad = {"id": episode["id"], "state": "preview_ready",
               "attempt_count": 1, "preview_fingerprint": "old-script",
               "voice_qa_passed": False, "mixed_audio_qa_passed": False}
        self.assertTrue(pq.eligible_retry(episode, bad, "revised-script"))
        self.assertFalse(pq.eligible_retry(episode, bad, "old-script"))
        bad["state"] = "reserved"
        self.assertFalse(pq.eligible_retry(episode, bad, "revised-script"))
        bad["state"] = "preview_ready"
        bad["attempt_count"] = 3
        self.assertFalse(pq.eligible_retry(episode, bad, "revised-script"))

    def test_user_requested_deep_male_voice_may_repair_unpublished_bright_preview(self):
        ep = {"id": "moto-old-bright-voice", "auto_publish": True,
              "voice_engine": "aidocmaker_deep",
              "voice_profile": "gustava_create_audio_deep_v1",
              "voice_revision_requested": True}
        previous = {"id": ep["id"], "state": "preview_ready",
                    "attempt_count": 2, "preview_fingerprint": "old-bright",
                    "voice_qa_passed": True, "mixed_audio_qa_passed": True}
        self.assertTrue(pq.eligible_retry(ep, previous, "new-deep"))
        previous["attempt_count"] = 4
        self.assertFalse(pq.eligible_retry(ep, previous, "new-deep"))
        previous["attempt_count"] = 2
        previous["voice_profile"] = "gustava_create_audio_deep_v1"
        self.assertFalse(pq.eligible_retry(ep, previous, "new-deep"))

    def test_owner_rejected_static_preview_can_revise_unpublished_visuals(self):
        ep={"id":"moto-helmet-fit-deep-20261030","auto_publish":False,
            "visual_revision_requested":True,
            "visual_revision_reason":"owner_rejected_static_helmet_coverage"}
        receipt={"id":ep["id"],"state":"preview_ready","attempt_count":1,
                 "preview_fingerprint":"static-scene",
                 "voice_qa_passed":True,"mixed_audio_qa_passed":True}
        self.assertTrue(pq.eligible_retry(ep,receipt,"adjusting-helmet-shot"))
        receipt["preview_fingerprint"]="adjusting-helmet-shot"
        self.assertFalse(pq.eligible_retry(ep,receipt,"adjusting-helmet-shot"))
        ep["visual_revision_reason"]="unapproved-visual-reason"
        self.assertFalse(pq.eligible_retry(ep,receipt,"new-static-scene"))

    def test_end_scene_only_adjusts_strap_can_retry_unpublished_preview(self):
        ep={"id":"moto-riding-ritual-deep-20261030",
            "auto_publish":False,
            "visual_revision_requested":True,
            "visual_revision_reason":"owner_rejected_end_clip_no_helmet_removal"}
        rec={"id":ep["id"],"state":"preview_ready","attempt_count":1,
             "preview_fingerprint":"early-action",
             "voice_qa_passed":True,"mixed_audio_qa_passed":True}
        self.assertTrue(pq.eligible_retry(ep,rec,"retimed-real-removal"))
        self.assertFalse(pq.eligible_retry(ep,rec,"early-action"))
        ep["visual_revision_reason"]="unreviewed"
        self.assertFalse(pq.eligible_retry(ep,rec,"retimed-real-removal"))

    def test_successful_audio_preview_is_never_remade(self):
        ep = {"id": "motorcycle-serial-02"}
        record = {"id": ep["id"], "state": "preview_ready",
                  "voice_qa_passed": True, "mixed_audio_qa_passed": True,
                  "attempt_count": 1, "preview_fingerprint": "past"}
        self.assertFalse(pq.eligible_retry(ep, record, "future"))

    def test_documentary_media_fix_can_replace_passed_unpublished_preview_once(self):
        episode={"id":"elspeth-beard-s1-e01",
                 "episode_series":{"historical_reconstruction":True}}
        receipt={"id":episode["id"],"state":"preview_ready","attempt_count":2,
                 "voice_qa_passed":True,"mixed_audio_qa_passed":True,
                 "preview_fingerprint":"misleading-footage"}
        self.assertTrue(pq.eligible_retry(episode,receipt,"correct-illustrations"))
        receipt["attempt_count"]=3
        self.assertTrue(pq.eligible_retry(episode,receipt,"new-still"))
        receipt["attempt_count"]=5
        self.assertFalse(pq.eligible_retry(episode,receipt,"new-still"))
        receipt["attempt_count"]=2
        self.assertFalse(pq.eligible_retry(episode,receipt,"misleading-footage"))

    def test_normal_good_video_cannot_reupload_due_to_irrelevant_code_change(self):
        ep={"id":"my-new-moto-short"}
        receipt={"id":ep["id"],"state":"preview_ready","attempt_count":1,
                 "voice_qa_passed":True,"mixed_audio_qa_passed":True,
                 "preview_fingerprint":"prior-version"}
        self.assertFalse(pq.eligible_retry(ep,receipt,"new-code"))

    def test_modified_script_changes_fingerprint(self):
        ep = {"id": "new-test-01", "narration": "Первое путешествие"}
        a = pq.preview_fingerprint(ep)
        ep["narration"] = "Второе путешествие"
        b = pq.preview_fingerprint(ep)
        self.assertNotEqual(a, b)
        self.assertEqual(len(a), 64)

    def test_bounded_stream_source_retry_only_after_confirmed_failed_run(self):
        item={"id":"moto-forest-4bd53e13fec4",
              "source_revision_requested":True,
              "source_revision_reason":"oversized_source_bounded_stream"}
        receipt={"id":item["id"],"state":"reserved","attempt_count":1,
                 "preview_fingerprint":"old-oversized-source"}
        self.assertTrue(pq.eligible_abandoned_source_retry(item,receipt,"new-stream-code","failure"))
        self.assertFalse(pq.eligible_abandoned_source_retry(item,receipt,"new-stream-code","in_progress"))
        self.assertFalse(pq.eligible_abandoned_source_retry(item,receipt,"old-oversized-source","failure"))
        receipt["attempt_count"]=3
        self.assertFalse(pq.eligible_abandoned_source_retry(item,receipt,"new-stream-code","failure"))
        receipt["attempt_count"]=1
        receipt["state"]="preview_ready"
        self.assertFalse(pq.eligible_abandoned_source_retry(item,receipt,"new-stream-code","failure"))

    def test_music_gain_fix_retries_only_verified_failed_unpublished_reservation(self):
        ep={"id":"moto-motocross-a5697d86523a",
            "auto_preview":True,"auto_publish":True,
            "technical_revision_requested":True,
            "technical_revision_reason":"safe_music_gain_range_fixed"}
        r={"id":ep["id"],"state":"reserved","attempt_count":2,
           "preview_fingerprint":"faulty-gain"}
        self.assertTrue(pq.eligible_abandoned_audio_config_retry(ep,r,"fixed-gain","failure"))
        self.assertFalse(pq.eligible_abandoned_audio_config_retry(ep,r,"fixed-gain","in_progress"))
        self.assertFalse(pq.eligible_abandoned_audio_config_retry(ep,r,"faulty-gain","failure"))
        ep["technical_revision_reason"]="unknown-reason"
        self.assertFalse(pq.eligible_abandoned_audio_config_retry(ep,r,"fixed-gain","failure"))
        ep["technical_revision_reason"]="safe_music_gain_range_fixed"
        r["attempt_count"]=3
        self.assertFalse(pq.eligible_abandoned_audio_config_retry(ep,r,"fixed-gain","failure"))
        r["attempt_count"]=2
        r["state"]="preview_ready"
        self.assertFalse(pq.eligible_abandoned_audio_config_retry(ep,r,"fixed-gain","failure"))

    def test_short_helmet_source_can_retry_only_after_confirmed_failure(self):
        ep={"id":"moto-helmet-fit-deep-20261030",
            "source_revision_requested":True,
            "source_revision_reason":"short_helmet_adjustment_rebalanced"}
        receipt={"id":ep["id"],"state":"reserved","attempt_count":2,
                 "preview_fingerprint":"oversized-clip"}
        self.assertTrue(pq.eligible_abandoned_source_retry(ep,receipt,"new-three-scenes","failure"))
        self.assertFalse(pq.eligible_abandoned_source_retry(ep,receipt,"new-three-scenes","in_progress"))
        self.assertFalse(pq.eligible_abandoned_source_retry(ep,receipt,"oversized-clip","failure"))
        receipt["state"]="preview_ready"
        self.assertFalse(pq.eligible_abandoned_source_retry(ep,receipt,"new-three-scenes","failure"))

    def test_exact_failed_worker_install_can_retry_private_deep_once(self):
        ep = {"id":"gustava-20-e03-20261030",
              "auto_preview":True,"auto_publish":False,
              "voice_engine":"aidocmaker_deep"}
        receipt = {"id":ep["id"],"state":"reserved","attempt_count":1,
                   "preview_fingerprint":"old-worker"}
        self.assertTrue(pq.eligible_abandoned_bootstrap_retry(
            ep,receipt,"fixed-worker",True))
        self.assertFalse(pq.eligible_abandoned_bootstrap_retry(
            ep,receipt,"fixed-worker",False))
        self.assertFalse(pq.eligible_abandoned_bootstrap_retry(
            ep,receipt,"old-worker",True))
        ep["auto_publish"]=True
        self.assertFalse(pq.eligible_abandoned_bootstrap_retry(
            ep,receipt,"fixed-worker",True))
        ep["auto_publish"]=False
        receipt["attempt_count"]=3
        self.assertFalse(pq.eligible_abandoned_bootstrap_retry(
            ep,receipt,"fixed-worker",True))
        receipt["attempt_count"]=1
        receipt["state"]="preview_ready"
        self.assertFalse(pq.eligible_abandoned_bootstrap_retry(
            ep,receipt,"fixed-worker",True))

    def test_new_genuine_deep_stock_precedes_private_revision_retries(self):
        from pathlib import Path
        source=Path(__file__).with_name("preview_queue.py").read_text(encoding="utf8")
        self.assertLess(source.index("# Genuine NEW originals have priority"),
                        source.index("# An explicit, unpublished narration repair"))
        self.assertIn('records[ep["id"]][0] is None',source)

    def test_reviewed_caption_fix_is_never_requeued_for_unapproved_rerender(self):
        from pathlib import Path
        import json
        catalog=json.loads((Path(__file__).parent/"episodes.json").read_text(encoding="utf8"))
        ep=next(e for e in catalog["episodes"] if e["id"]=="gustava-20-s02-20261030")
        self.assertIs(ep["auto_publish"],True)
        self.assertIs(ep["visual_revision_requested"],False)
        self.assertIs(ep["caption_fit_required"],True)
        self.assertEqual(ep["visual_revision_status"],"assistant_checked_passed")
        self.assertEqual(ep["reviewed_artifact_run_id"],"41234971139")
        from preview_queue import eligible_retry,preview_fingerprint
        receipt={"id":ep["id"],"state":"preview_ready","attempt_count":4,
                 "preview_fingerprint":"old-caption","voice_qa_passed":True,
                 "mixed_audio_qa_passed":True,
                 "voice_profile":"gustava_create_audio_deep_v1"}
        self.assertFalse(eligible_retry(ep,receipt,preview_fingerprint(ep)))

    def test_fourth_private_retry_needs_actual_replacement_and_failed_run(self):
        ep={"id":"gustava-20-f01-20261030","auto_preview":True,
            "auto_publish":False,"voice_engine":"aidocmaker_deep",
            "source_revision_requested":True,
            "source_revision_reason":"frozen_source_replaced",
            "source_replacement_proof":{
                "old_source_id":"28209492","new_source_id":"9606781",
                "failed_run_id":"41233361222","old_failure":"VISUAL_FROZEN_SEGMENT"},
            "footage":[
                {"source_page":"https://www.pexels.com/video/old-gloves-6435393/"},
                {"source_page":"https://www.pexels.com/video/new-helmet-9606781/"}]}
        receipt={"id":ep["id"],"state":"reserved","attempt_count":3,
                 "run_id":"41233361222","preview_fingerprint":"old-frozen"}
        check=lambda: pq.eligible_abandoned_source_retry(
            ep,receipt,"new-different-scene","failure")
        self.assertTrue(check())
        self.assertFalse(pq.eligible_abandoned_source_retry(
            ep,receipt,"new-different-scene","cancelled"))
        receipt["attempt_count"]=4
        self.assertFalse(check())
        receipt["attempt_count"]=3
        ep["auto_publish"]=True
        self.assertFalse(check())
        ep["auto_publish"]=False
        ep["source_replacement_proof"]["new_source_id"]="28209492"
        self.assertFalse(check())
        ep["source_replacement_proof"]["new_source_id"]="12405712"
        ep["source_replacement_proof"]["failed_run_id"]="wrong"
        self.assertFalse(check())
        ep["source_replacement_proof"]["failed_run_id"]="41233361222"
        ep["footage"][1]["source_page"]="https://www.pexels.com/video/old-helmet-28209492/"
        self.assertFalse(check())

    def test_missing_or_corrupt_registry_fails_closed(self):
        with self.assertRaises(RuntimeError):
            pq.decode_history(None)
        with self.assertRaises(RuntimeError):
            pq.decode_history({"sha": "x", "content": ""})

    def test_finish_409_conflict_retries_identical_reservation_not_new_render(self):
        import base64,json,os,tempfile
        from pathlib import Path
        from unittest.mock import patch
        slug="test-deep-conflict-01"
        old={"id":slug,"run_id":"4100","state":"reserved",
             "preview_fingerprint":"pinned-source","deep_source_sha256":"a"*64}
        def record(sha="sha1",**overrides):
            d={**old,**overrides}
            return {"sha":sha,"content":base64.b64encode(json.dumps(d).encode()).decode()}
        raw={"episode_id":slug,"passed":True,"status":"passed",
             "final_word_present":True,"lexical_coverage":1.0,
             "male_voice_verified":True,"voice_profile":pq.REQUIRED_MALE_PROFILE}
        mixed={"episode_id":slug,"source":"FINAL_MIXED_MP4",
               "passed":True,"status":"passed","final_word_present":True,
               "numerics_match":True,"lexical_coverage":1.0}
        with tempfile.TemporaryDirectory() as root:
            a=Path(root)/"raw.json";b=Path(root)/"mixed.json"
            a.write_text(json.dumps(raw));b.write_text(json.dumps(mixed))
            with patch.dict(os.environ,{"GITHUB_RUN_ID":"4100"}), \
                 patch.object(pq,"api",side_effect=[record("sha1"),record("sha2"),record("sha3")]), \
                 patch.object(pq,"store",side_effect=[
                     RuntimeError("GitHub queue operation failed HTTP 409"),
                     RuntimeError("GitHub queue operation failed HTTP 409"),
                     {"commit":{"sha":"done"}}]) as store, \
                 patch("time.sleep",return_value=None):
                pq.finish(slug,a,b)
                self.assertEqual(store.call_count,3)
                self.assertEqual([x.args[3] for x in store.call_args_list],
                                 ["sha1","sha2","sha3"])
                self.assertEqual(store.call_args.kwargs,{})
                self.assertTrue(store.call_args.args[1]["voice_qa_passed"])
                self.assertTrue(store.call_args.args[1]["mixed_audio_qa_passed"])

    def test_finish_409_conflict_never_overwrites_changed_run(self):
        import base64,json,os,tempfile
        from pathlib import Path
        from unittest.mock import patch
        slug="test-deep-conflict-02"
        original={"id":slug,"run_id":"4100","state":"reserved",
                  "preview_fingerprint":"original"}
        def wrap(record,sha):
            return {"sha":sha,"content":base64.b64encode(
                json.dumps(record).encode()).decode()}
        with tempfile.TemporaryDirectory() as folder:
            raw=Path(folder)/"voice.json"
            raw.write_text("{}")
            with patch.dict(os.environ,{"GITHUB_RUN_ID":"4100"}), \
                 patch.object(pq,"api",side_effect=[
                     wrap(original,"sha1"),
                     wrap({**original,"run_id":"evil-run"},"sha2")]), \
                 patch.object(pq,"store",side_effect=RuntimeError(
                     "GitHub queue operation failed HTTP 409")) as store, \
                 patch("time.sleep",return_value=None):
                with self.assertRaisesRegex(RuntimeError,"receipt changed"):
                    pq.finish(slug,raw)
                self.assertEqual(store.call_count,1)

    def test_receipt_filename_validation(self):
        self.assertEqual(pq.item_path("jump-second-01"),
                         "render-receipts/jump-second-01.json")
        with self.assertRaises(ValueError):
            pq.item_path("../exploit")
        with self.assertRaises(ValueError):
            pq.item_path("")

if __name__ == "__main__":
    unittest.main()
