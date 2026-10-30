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
        self.assertTrue(w.should_replenish(state,[],0,now))

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

if __name__=="__main__":
    unittest.main()
