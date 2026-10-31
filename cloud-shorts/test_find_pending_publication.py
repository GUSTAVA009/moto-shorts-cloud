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
