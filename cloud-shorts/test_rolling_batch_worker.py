"""No-network tests of rolling ten publisher-status watcher."""
from datetime import datetime, timedelta, timezone
import unittest
import rolling_batch_worker as w
import rolling_batches as b

class RollingBatchWorkerTests(unittest.TestCase):
    def test_full_buffer_needs_no_poll_refill(self):
        now=datetime(2026,10,30,tzinfo=timezone.utc)
        state,_=b.reconcile(None,[])
        state["last_replenish_request_at"]=(now-timedelta(hours=2)).isoformat()
        self.assertFalse(w.should_replenish(state,[],10,now))
        self.assertTrue(w.should_replenish(state,[],9,now))
        self.assertTrue(w.should_replenish(state,[],7,now))
        self.assertTrue(w.should_replenish(state,[],6,now))
        self.assertTrue(w.should_replenish(state,[],0,now))

    def test_refill_at_nine_is_distinct_from_low_stock_alarm_seven(self):
        from datetime import timedelta
        now=datetime(2026,10,30,tzinfo=timezone.utc)
        state,_=b.reconcile(None,[])
        state["last_replenish_request_at"]=(now-timedelta(hours=2)).isoformat()
        self.assertEqual(w.MIN_BUFFER_SCHEDULED,7)
        self.assertEqual(w.REFILL_AT_OR_BELOW_SCHEDULED,9)
        self.assertFalse(w.should_replenish(state,[],10,now))
        self.assertTrue(w.should_replenish(state,[],9,now))
        self.assertTrue(w.should_replenish(state,[],8,now))
        state["last_replenish_request_at"]=(now-timedelta(minutes=20)).isoformat()
        self.assertFalse(w.should_replenish(state,[],9,now))

    def test_9th_and_10th_start_refill_even_with_full_queue(self):
        now=datetime(2026,10,30,tzinfo=timezone.utc)
        state,_=b.reconcile(None,[])
        state["last_replenish_request_at"]=now.isoformat()
        self.assertTrue(w.should_replenish(state,["stage_next_ten"],10,now))
        self.assertTrue(w.should_replenish(state,["promote_next_ten"],10,now))

    def test_low_queue_throttled(self):
        now=datetime(2026,10,30,tzinfo=timezone.utc)
        state,_=b.reconcile(None,[])
        state["last_replenish_request_at"]=(now-timedelta(minutes=30)).isoformat()
        self.assertFalse(w.should_replenish(state,[],0,now))
        state["last_replenish_request_at"]=(now-timedelta(minutes=46)).isoformat()
        self.assertTrue(w.should_replenish(state,[],0,now))

    def test_corrupt_ledger_never_reinitialized(self):
        with self.assertRaises(RuntimeError):
            w.read_state({"sha":"1","content":""})
        with self.assertRaises(RuntimeError):
            w.read_state({"sha":"1","content":"?"})

    def test_no_extra_ledger_commit_without_new_publication(self):
        now=datetime(2026,10,30,tzinfo=timezone.utc)
        state,_=b.reconcile(None,[],now=now.isoformat())
        self.assertFalse(w.needs_persist(state,dict(state),[],now))
        self.assertTrue(w.needs_persist(None,state,[],now))
        self.assertTrue(w.needs_persist(state,dict(state),["stage_next_ten"],now))
        self.assertTrue(w.needs_persist(state,dict(state),[],now+timedelta(hours=7)))



    def test_full_buffer_still_refills_when_separate_reviewed_mp4_reserve_empty(self):
        now=datetime(2026,11,1,tzinfo=timezone.utc)
        state,_=b.reconcile(None,[])
        state["last_replenish_request_at"]=(now-timedelta(hours=2)).isoformat()
        self.assertTrue(w.should_replenish(state,[],10,now,0))
        self.assertTrue(w.should_replenish(state,[],10,now,9))
        self.assertFalse(w.should_replenish(state,[],10,now,10))
        state["last_replenish_request_at"]=(now-timedelta(minutes=5)).isoformat()
        self.assertFalse(w.should_replenish(state,[],10,now,0))

    def test_only_real_unqueued_deep_reviewed_mp4_counts_as_reserve(self):
        ep={"id":"fresh-moto-01", "auto_publish":True,
            "voice_engine":"aidocmaker_deep",
            "reviewed_mp4_sha256":"a"*64,
            "reviewed_artifact_run_id":"42",
            "visual_director_version":3,
            "visual_revision_status":"assistant_checked_passed",
            "scene_script_anchors":[{"source":"clip_0","action":"riding",
                                     "spoken_anchor":"мотоцикл"}],
            "title":"Мотоцикл едет", "narration":"Мотоцикл едет по трассе.",
            "editorial":{"bike":"offroad-trail-motorcycle"}}
        receipt={"id":"fresh-moto-01","state":"preview_ready",
                 "voice_qa_passed":True,"mixed_audio_qa_passed":True,
                 "voice_profile":"gustava_create_audio_deep_v1",
                 "male_voice_verified":True,"run_id":"42"}
        artifact={"name":"daily-preview-fresh-moto-01-42","expired":False}
        path="render-receipts/fresh-moto-01.json"
        count=w.count_unqueued_reviewed_mp4
        self.assertEqual(count({"episodes":[ep]},[receipt],[artifact],[path]),1)
        self.assertEqual(count({"episodes":[ep]},[receipt],[artifact],
                               [path,"buffer-publication-receipts/fresh-moto-01.json"]),0)
        self.assertEqual(count({"episodes":[ep]},[receipt],
                               [dict(artifact,expired=True)],[path]),0)
        self.assertEqual(count({"episodes":[dict(ep,auto_publish=False)]},
                               [receipt],[artifact],[path]),0)
        self.assertEqual(count({"episodes":[dict(ep,reviewed_mp4_sha256="")]},
                               [receipt],[artifact],[path]),0)
        self.assertEqual(count({"episodes":[ep]},
                               [dict(receipt,mixed_audio_qa_passed=False)],
                               [artifact],[path]),0)
        self.assertEqual(count({"episodes":[dict(ep,visual_review_failed=True)]},
                               [receipt],[artifact],[path]),0)

if __name__=="__main__":
    unittest.main()
