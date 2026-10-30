"""Prove exact ninth/tenth milestone, permanence and no false publication counts."""
import unittest
from datetime import datetime, timedelta, timezone

import rolling_batches as b


def sent(n):
    origin = datetime(2026, 10, 30, tzinfo=timezone.utc)
    return [{"id": f"buffer-sent-{i:03d}", "sentAt":
             (origin + timedelta(minutes=90*i)).isoformat()}
            for i in range(1, n+1)]


class RollingTenTests(unittest.TestCase):
    def test_initial_batch_is_ten_unique_complete_scripts(self):
        state, events = b.reconcile(None, [], now="2026-10-30T00:00:00Z")
        self.assertEqual(events, ["bootstrap_active_ten"])
        self.assertEqual(len(state["active_batch"]["scripts"]), 10)
        self.assertEqual(state["verified_sent_count"], 0)
        drafts = state["active_batch"]["scripts"]
        self.assertEqual(len({s["_reserve_id"] for s in drafts}), 10)
        self.assertEqual(len({s["theme"] for s in drafts}), 10)
        self.assertEqual(len({s["narration"] for s in drafts}), 10)
        self.assertEqual(state["next_cursor"], 10)

    def test_nine_stages_ten_and_tenth_promotes(self):
        s, _ = b.reconcile(None, sent(8))
        self.assertIsNone(s["pending_batch"])
        s, events = b.reconcile(s, sent(9))
        self.assertEqual(events, ["stage_next_ten"])
        self.assertEqual(s["verified_sent_count"], 9)
        self.assertEqual(len(s["pending_batch"]["scripts"]), 10)
        self.assertEqual(s["pending_batch"]["number"], 1)
        old_active = s["active_batch"]["scripts"]
        s, events = b.reconcile(s, sent(10))
        self.assertEqual(events, ["promote_next_ten"])
        self.assertEqual(s["active_batch"]["number"], 1)
        self.assertIsNone(s["pending_batch"])
        self.assertFalse(set(x["_reserve_id"] for x in old_active) &
                         set(x["_reserve_id"] for x in s["active_batch"]["scripts"]))
        same, events = b.reconcile(s, sent(10))
        self.assertEqual(events, [])
        self.assertEqual(same["verified_sent_count"], 10)
        self.assertEqual(same["next_cursor"], s["next_cursor"])

    def test_twenty_publications_and_recovery_if_two_arrive_at_once(self):
        s, _ = b.reconcile(None, sent(8))
        s, events = b.reconcile(s, sent(12))
        self.assertEqual(events, ["stage_next_ten", "promote_next_ten"])
        self.assertEqual(s["active_batch"]["number"], 1)
        s, events = b.reconcile(s, sent(20))
        self.assertEqual(events, ["stage_next_ten", "promote_next_ten"])
        self.assertEqual(s["active_batch"]["number"], 2)
        self.assertEqual(s["verified_sent_count"], 20)
        self.assertEqual(s["next_cursor"], 30)

    def test_scheduled_posts_never_count(self):
        s, events = b.reconcile(None, [])
        self.assertEqual(s["verified_sent_count"], 0)
        self.assertIsNone(s["pending_batch"])
        self.assertEqual(b.progress(s, 9)["current_pack_progress"], 0)
        self.assertEqual(b.progress(s, 9)["buffer_scheduled_posts"], 9)

    def test_malformed_sent_data_blocks_false_advances(self):
        s, _ = b.reconcile(None, sent(8))
        for bad in ([{"id": "x"}], [{"sentAt": "2026-10-30T10:00:00Z"}],
                    [{"id": "x", "sentAt": "not-a-date"}]):
            with self.assertRaises(ValueError):
                b.reconcile(s, bad)
        self.assertEqual(s["verified_sent_count"], 8)

    def test_duplicate_posts_never_double_count(self):
        s, events = b.reconcile(None, sent(9) + [sent(9)[-1]])
        self.assertEqual(s["verified_sent_count"], 9)
        self.assertEqual(events.count("stage_next_ten"), 1)
        s2, events = b.reconcile(s, sent(9))
        self.assertEqual(events, [])
        self.assertEqual(s2["verified_sent_count"], 9)

    def test_already_materialized_script_is_excluded(self):
        s, _ = b.reconcile(None, [])
        reserve_id = s["active_batch"]["scripts"][0]["_reserve_id"]
        remaining = b.selected_scripts(s, {"episodes":[{"story_reserve_id":reserve_id}]})
        self.assertEqual(len(remaining), 9)
        self.assertNotIn(reserve_id, {x["_reserve_id"] for x in remaining})

    def test_staged_scripts_not_active_until_tenth(self):
        s, _ = b.reconcile(None, sent(9))
        active = {x["_reserve_id"] for x in b.selected_scripts(s, {"episodes":[]})}
        next_ids = {x["_reserve_id"] for x in s["pending_batch"]["scripts"]}
        self.assertFalse(active & next_ids)

    def test_corrupt_ledger_is_fail_closed(self):
        s, _ = b.reconcile(None, [])
        s["active_batch"]["scripts"].pop()
        with self.assertRaisesRegex(ValueError, "Invalid editorial script"):
            b.reconcile(s, [])


if __name__ == "__main__":
    unittest.main()
