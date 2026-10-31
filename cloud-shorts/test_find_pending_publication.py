"""Offline tests of the resumable publishing candidate selector."""
import unittest
import find_pending_publication as q


class BacklogTests(unittest.TestCase):
    def test_reviewed_real_first_ride_enters_buffer_only_with_exposed_qa(self):
        import json
        from pathlib import Path
        cat=json.loads((Path(__file__).parent/"episodes.json").read_text(encoding="utf8"))
        episode=next(ep for ep in cat["episodes"] if ep["id"]=="gustava-20-s02-20261030")
        self.assertTrue(episode["auto_publish"])
        self.assertFalse(episode["visual_revision_requested"])
        self.assertEqual(episode["visual_revision_status"],"assistant_checked_passed")
        self.assertEqual([x["source"] for x in episode["scene_script_anchors"]],
                         ["clip_0","clip_1"])
        from visual_director import verify_scene_script_anchors
        self.assertEqual(verify_scene_script_anchors(episode),["clip_0","clip_1"])
        self.assertEqual(len(episode["reviewed_mp4_sha256"]),64)
        run=episode["reviewed_artifact_run_id"]
        artifact=f"daily-preview-{episode['id']}-{run}"
        receipt={"id":episode["id"],"state":"preview_ready",
                 "voice_qa_passed":True,"mixed_audio_qa_passed":True,
                 "voice_profile":"gustava_create_audio_deep_v1",
                 "male_voice_verified":True,"run_id":run}
        self.assertEqual(q.select({"episodes":[episode]},[receipt],set(),
                       [{"name":artifact,"expired":False}]),
                       (int(run),episode["id"],artifact))
        self.assertIsNone(q.select({"episodes":[episode]},[receipt],{episode["id"]},
                       [{"name":artifact,"expired":False}]))

    def test_exact_reviewed_deep_victory_short_can_enter_buffer_once(self):
        import json
        from pathlib import Path
        data=json.loads((Path(__file__).parent/"episodes.json").read_text(encoding="utf8"))
        ep=next(e for e in data["episodes"] if e["id"]=="gustava-20-f06-20261030")
        self.assertTrue(ep["auto_publish"])
        self.assertEqual(ep["reviewed_mp4_sha256"],"f165214a06309baa79d991345a2b9d21d75156cfc713bff95f38a30d67a31ee5")
        run=ep["reviewed_artifact_run_id"]
        receipt={"id":ep["id"],"state":"preview_ready",
                 "voice_qa_passed":True,"mixed_audio_qa_passed":True,
                 "voice_profile":"gustava_create_audio_deep_v1",
                 "male_voice_verified":True,"run_id":run}
        artifact={"name":f"daily-preview-{ep['id']}-{run}","expired":False}
        self.assertEqual(q.select({"episodes":[ep]},[receipt],set(),[artifact]),
                         (int(run),ep["id"],artifact["name"]))
        self.assertIsNone(q.select({"episodes":[ep]},[receipt],{ep["id"]},[artifact]))

    def test_exact_urban_deep_private_preview_released_only_after_frame_review(self):
        import json
        from pathlib import Path
        from visual_director import verify_scene_script_anchors
        data=json.loads((Path(__file__).parent/"episodes.json").read_text(encoding="utf8"))
        ep=next(e for e in data["episodes"] if e["id"]=="gustava-20-e04-20261030")
        self.assertTrue(ep["auto_publish"])
        self.assertFalse(ep["source_revision_requested"])
        self.assertEqual(ep["reviewed_mp4_sha256"],
                         "9b63292edf78d5f085f1d500bc6e02bd79c1e7fc70b6a9ecdcbdcff115513488")
        self.assertEqual(verify_scene_script_anchors(ep),["clip_0","clip_1"])
        receipt={"id":ep["id"],"state":"preview_ready",
                 "voice_qa_passed":True,"mixed_audio_qa_passed":True,
                 "voice_profile":"gustava_create_audio_deep_v1",
                 "male_voice_verified":True,"run_id":ep["reviewed_artifact_run_id"]}
        artifact={"name":f"daily-preview-{ep['id']}-{receipt['run_id']}","expired":False}
        self.assertEqual(q.select({"episodes":[ep]},[receipt],set(),[artifact]),
                         (int(receipt["run_id"]),ep["id"],artifact["name"]))
        self.assertIsNone(q.select({"episodes":[ep]},[receipt],{ep["id"]},[artifact]))
        mismatched=dict(ep,scene_script_anchors=[
            dict(ep["scene_script_anchors"][0],action="motorcycle_city_pov"),
            ep["scene_script_anchors"][1]])
        with self.assertRaisesRegex(ValueError,"VISUAL_BEATS_OFF_SCRIPT"):
            verify_scene_script_anchors(mismatched)

    def test_verified_engine_workshop_original_deep_release_is_one_time(self):
        import json
        from pathlib import Path
        from visual_director import verify_scene_script_anchors
        catalog=json.loads((Path(__file__).parent/"episodes.json").read_text(encoding="utf8"))
        episode=next(x for x in catalog["episodes"] if x["id"]=="gustava-20-f04-20261030")
        self.assertTrue(episode["auto_publish"])
        self.assertEqual(episode["reviewed_mp4_sha256"],
                         "c8335445059503e4e006e987fdcc0f40a2952d2ea4f66fec7da483689c04e2b3")
        self.assertEqual(episode["reviewed_artifact_run_id"],"41240927449")
        self.assertEqual(verify_scene_script_anchors(episode),["clip_0","clip_1"])
        receipt={"id":episode["id"],"state":"preview_ready",
                 "voice_qa_passed":True,"mixed_audio_qa_passed":True,
                 "voice_profile":"gustava_create_audio_deep_v1",
                 "male_voice_verified":True,"run_id":episode["reviewed_artifact_run_id"]}
        artifact={"name":f"daily-preview-{episode['id']}-{receipt['run_id']}","expired":False}
        self.assertEqual(q.select({"episodes":[episode]},[receipt],set(),[artifact]),
                         (int(receipt["run_id"]),episode["id"],artifact["name"]))
        self.assertIsNone(q.select({"episodes":[episode]},[receipt],{episode["id"]},[artifact]))

    def test_exact_sand_offroad_deep_release_is_review_pinned_and_nonduplicate(self):
        import json
        from pathlib import Path
        from visual_director import verify_scene_script_anchors
        cat=json.loads((Path(__file__).parent/"episodes.json").read_text(encoding="utf8"))
        ep=next(x for x in cat["episodes"] if x["id"]=="gustava-20-e05-20261030")
        self.assertTrue(ep["auto_publish"])
        self.assertEqual(ep["reviewed_mp4_sha256"],
                         "8b9b9eed6e9b7ca382afe07fe49ccf035ce1de7ec78113956ee897156701be47")
        self.assertEqual(ep["reviewed_artifact_run_id"],"41241069846")
        self.assertEqual(verify_scene_script_anchors(ep),["clip_0","clip_1"])
        proof={"id":ep["id"],"state":"preview_ready",
               "voice_qa_passed":True,"mixed_audio_qa_passed":True,
               "voice_profile":"gustava_create_audio_deep_v1",
               "male_voice_verified":True,"run_id":ep["reviewed_artifact_run_id"]}
        artifact={"name":f"daily-preview-{ep['id']}-{proof['run_id']}","expired":False}
        self.assertEqual(q.select({"episodes":[ep]},[proof],set(),[artifact]),
                         (int(proof["run_id"]),ep["id"],artifact["name"]))
        self.assertIsNone(q.select({"episodes":[ep]},[proof],{ep["id"]},[artifact]))

    def test_real_motocross_jump_two_races_no_fake_repetition(self):
        import json
        from pathlib import Path
        from visual_director import verify_scene_script_anchors
        cat=json.loads((Path(__file__).parent/"episodes.json").read_text(encoding="utf8"))
        ep=next(e for e in cat["episodes"] if e["id"]=="gustava-20-p02-20261030")
        self.assertTrue(ep["auto_publish"])
        self.assertFalse(ep["source_revision_requested"])
        self.assertEqual(ep["reviewed_mp4_sha256"],
                         "68beafcd34710b62bdc82b5e4ad0474e0b445286a1852df553f53e97b740e253")
        self.assertEqual(verify_scene_script_anchors(ep),["clip_0","clip_1"])
        receipt={"id":ep["id"],"state":"preview_ready",
                 "voice_qa_passed":True,"mixed_audio_qa_passed":True,
                 "voice_profile":"gustava_create_audio_deep_v1",
                 "male_voice_verified":True,"run_id":ep["reviewed_artifact_run_id"]}
        artifact={"name":f"daily-preview-{ep['id']}-{receipt['run_id']}","expired":False}
        self.assertEqual(q.select({"episodes":[ep]},[receipt],set(),[artifact]),
                         (int(receipt["run_id"]),ep["id"],artifact["name"]))
        self.assertIsNone(q.select({"episodes":[ep]},[receipt],{ep["id"]},[artifact]))

    def test_only_new_unpublished_qa_passed_artifacts(self):
        catalog={"episodes":[{"id":"a-new-01","auto_publish":True,"voice_engine":"aidocmaker_deep",
                             "title":"Мотоцикл на трассе",
                             "narration":"Мотоцикл проходит поворот.",
                             "editorial":{"bike":"offroad-trail-motorcycle"}},
                             {"id":"old-ep-02","auto_publish":False}]}
        receipts=[{"id":"a-new-01","state":"preview_ready","voice_qa_passed":True,"mixed_audio_qa_passed":True,"voice_profile":"gustava_create_audio_deep_v1","male_voice_verified":True,"run_id":"42"},
                  {"id":"old-ep-02","state":"preview_ready","voice_qa_passed":True,"mixed_audio_qa_passed":True,"run_id":"51"}]
        assets=[{"name":"daily-preview-a-new-01-42","expired":False},
                {"name":"daily-preview-old-ep-02-51","expired":False}]
        self.assertEqual(q.select(catalog,receipts,set(),assets),(42,"a-new-01","daily-preview-a-new-01-42"))
        self.assertIsNone(q.select(catalog,receipts,{"a-new-01"},assets))

    def test_rejected_and_unreviewed_v3_never_selected(self):
        ep={"id":"scene-first-01","auto_publish":True,
            "voice_engine":"aidocmaker_deep","visual_director_version":3,
            "visual_revision_status":"assistant_checked_passed",
            "scene_script_anchors":[{"source":"clip_0","action":"riding","spoken_anchor":"мотоцикл"}],
            "title":"Мотоцикл едет по дороге",
            "narration":"Мотоцикл едет по дороге.",
            "editorial":{"bike":"touring-motorcycle"}}
        catalog={"episodes":[ep]}
        r=[{"id":ep["id"],"state":"preview_ready","voice_qa_passed":True,
            "mixed_audio_qa_passed":True,"voice_profile":"gustava_create_audio_deep_v1",
            "male_voice_verified":True,"run_id":"100"}]
        arts=[{"name":"daily-preview-scene-first-01-100","expired":False}]
        self.assertEqual(q.select(catalog,r,set(),arts),(100,ep["id"],arts[0]["name"]))
        ep["visual_review_failed"]=True
        self.assertIsNone(q.select(catalog,r,set(),arts))
        del ep["visual_review_failed"]
        ep["visual_revision_status"]="assistant_checked_passed_pending_owner"
        self.assertIsNone(q.select(catalog,r,set(),arts))
        ep["visual_revision_status"]="assistant_checked_passed"
        ep["visual_revision_requested"]=True
        self.assertIsNone(q.select(catalog,r,set(),arts))

    def test_previous_gravelly_v3_voice_is_rejected(self):
        catalog = {"episodes": [{"id":"a-new-01","auto_publish":True,
            "voice_engine":"aidocmaker_deep","title":"Мотоцикл","narration":"Мотоцикл.",
            "editorial":{"bike":"offroad-trail-motorcycle"}}]}
        receipt = [{"id":"a-new-01","state":"preview_ready",
            "voice_qa_passed":True,"mixed_audio_qa_passed":True,
            "voice_profile":"gustava_male_deep_v3",
            "male_voice_verified":True,"run_id":"42"}]
        artifacts = [{"name":"daily-preview-a-new-01-42","expired":False}]
        self.assertIsNone(q.select(catalog,receipt,set(),artifacts))

    def test_old_v2_voice_profile_no_longer_valid(self):
        catalog={"episodes":[{"id":"a-new-01","auto_publish":True,
                              "voice_engine":"aidocmaker_deep",
                              "title":"Мотоцикл на трассе",
                              "narration":"Мотоцикл проходит поворот.",
                              "editorial":{"bike":"offroad-trail-motorcycle"}}]}
        receipts=[{"id":"a-new-01","state":"preview_ready",
                   "voice_qa_passed":True,"mixed_audio_qa_passed":True,
                   "voice_profile":"gustava_male_deep_v2",
                   "male_voice_verified":True,"run_id":"42"}]
        artifacts=[{"name":"daily-preview-a-new-01-42","expired":False}]
        self.assertIsNone(q.select(catalog,receipts,set(),artifacts))

    def test_old_bright_male_profile_never_auto_releases(self):
        catalog={"episodes":[{"id":"bright-voice","auto_publish":True,"voice_engine":"aidocmaker_deep",
                             "title":"Мотоцикл на трассе", "narration":"Мотоцикл едет.",
                             "editorial":{"bike":"offroad-trail-motorcycle"}}]}
        receipts=[{"id":"bright-voice","state":"preview_ready",
                   "voice_qa_passed":True,"mixed_audio_qa_passed":True,"run_id":"54"}]
        assets=[{"name":"daily-preview-bright-voice-54","expired":False}]
        self.assertIsNone(q.select(catalog,receipts,set(),assets))

    def test_retired_robotic_voice_cannot_publish_even_if_old_qa_passed(self):
        catalog={"episodes":[{"id":"piper-old","auto_publish":True,"voice_engine":"piper_ru"}]}
        receipts=[{"id":"piper-old","state":"preview_ready",
                   "voice_qa_passed":True,"mixed_audio_qa_passed":True,"run_id":"20"}]
        assets=[{"name":"daily-preview-piper-old-20","expired":False}]
        self.assertIsNone(q.select(catalog,receipts,set(),assets))

    def test_absent_qa_receipt_or_expired_artifact_refused(self):
        catalog={"episodes":[{"id":"a-new-01","auto_publish":True,"voice_engine":"aidocmaker_deep",
                             "title":"Мотоцикл на трассе",
                             "narration":"Мотоцикл проходит поворот.",
                             "editorial":{"bike":"offroad-trail-motorcycle"}}]}
        rs=[{"id":"a-new-01","state":"preview_ready","run_id":"42"}]
        assets=[{"name":"daily-preview-a-new-01-42","expired":False}]
        self.assertIsNone(q.select(catalog,rs,set(),assets))
        rs[0]["voice_qa_passed"]=True
        self.assertIsNone(q.select(catalog,rs,set(),assets))
        rs[0]["mixed_audio_qa_passed"]=True
        assets[0]["expired"]=True
        self.assertIsNone(q.select(catalog,rs,set(),assets))


if __name__=="__main__":
    unittest.main()
