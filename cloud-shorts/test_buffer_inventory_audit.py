import unittest
import buffer_inventory_audit as a

class BufferPostInventoryTests(unittest.TestCase):
    def test_live_sent_error_and_missing_are_distinguished(self):
        receipts=[
          {"episode":"a","buffer_post_id":"aa","state":"queued","due_at":"2026-10-29T18:00Z"},
          {"episode":"b","buffer_post_id":"bb","state":"queued","due_at":"2026-10-29T19:00Z"},
          {"episode":"c","buffer_post_id":"cc","state":"queued","due_at":"2026-10-29T20:00Z"}
        ]
        posts=[{"id":"aa","status":"sent"},{"id":"bb","status":"error"}]
        x=a.check_receipts(receipts,posts)
        self.assertEqual(x["receipt_posts_by_buffer_status"],{"sent":1,"error":1})
        self.assertEqual(x["missing_count"],1)
        self.assertEqual(x["missing_receipted_posts"][0]["post_id"],"cc")
        self.assertEqual(x["latest_matching_receipts"][0]["post_id"], "bb")
        self.assertEqual(x["latest_matching_receipts"][0]["live_status"], "error")

    def test_real_publisher_success_triggers_independent_live_queue_audit(self):
        from pathlib import Path
        workflow = (Path(__file__).parent.parent /
                    ".github/workflows/buffer-inventory-audit.yml").read_text("utf8")
        self.assertIn("workflows: ['GUSTAVA - Verified Shorts to Buffer Queue']", workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", workflow)
        self.assertIn("python3 cloud-shorts/buffer_inventory_audit.py", workflow)
        self.assertNotIn("createPost", workflow)

    def test_graphql_inventory_uses_only_reads_and_checks_all_pages(self):
        response={"posts":{"edges":[{"node":{"id":"x","status":"needs_approval"}}],
                           "pageInfo":{"hasNextPage":False}}}
        queries=[]
        def fetch(q):
            queries.append(q)
            return response
        self.assertEqual(a.live_post_inventory(fetch)[0]["status"],"needs_approval")
        self.assertIn("posts(first:100",queries[0])
        self.assertNotIn("mutation",queries[0])
        response["posts"]["pageInfo"]["hasNextPage"]=True
        with self.assertRaisesRegex(RuntimeError,"TRUNCATED"):
            a.live_post_inventory(fetch)

if __name__=="__main__":
    unittest.main()
