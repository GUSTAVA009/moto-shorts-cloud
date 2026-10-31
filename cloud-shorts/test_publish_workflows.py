"""Safety regression: Buffer alone handles automatic public delivery."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent.parent


def source(relative):
    return (ROOT / relative).read_text(encoding="utf8")


class PublisherShellTests(unittest.TestCase):
    def test_buffer_receives_both_independent_audio_qa_reports(self):
        workflow = source(".github/workflows/buffer-backlog.yml")
        self.assertIn("buffer_autopublish.py", workflow)
        self.assertRegex(workflow, r'--voice-qa[^\n]*\\\s*\n\s*--mixed-qa')
        self.assertIn("vars.BUFFER_AUTO_PUBLISH_ENABLED != 'false'", workflow)
        self.assertIn("BUFFER_AUTO_PUBLISH_ENABLED: ${{ vars.BUFFER_AUTO_PUBLISH_ENABLED || 'true' }}", workflow)

    def test_approved_catalog_change_wakes_buffer_sender(self):
        # A normal catalog PR merge must not leave an editorially approved
        # private MP4 stranded until the next arbitrary cron window.
        workflow = source(".github/workflows/buffer-backlog.yml")
        self.assertIn("- 'cloud-shorts/episodes.json'", workflow)
        self.assertIn("Select one original, QA-passed, never-published video", workflow)
        self.assertIn("find_pending_buffer.py", workflow)

    def test_daily_generation_never_directly_posts(self):
        workflow = source(".github/workflows/daily-preview.yml").casefold()
        self.assertNotIn("publora", workflow)
        self.assertNotIn("buffer_autopublish.py", workflow)
        self.assertNotIn("publishnow", workflow)
        self.assertIn("upload-artifact@v4", workflow)

    def test_passed_mp4_dispatches_verified_sender_without_deep_workflow_chain(self):
        preview = source(".github/workflows/daily-preview.yml")
        self.assertIn("actions: write", preview)
        self.assertIn("success() && steps.pick.outputs.has_job == 'true'", preview)
        self.assertIn("/actions/workflows/buffer-backlog.yml/dispatches", preview)
        self.assertIn('"ref":"main"', preview)
        self.assertIn("BUFFER_VERIFIED_DISPATCH_CONFIRMED", preview)
        self.assertNotIn("buffer_autopublish.py --episode", preview)

    def test_buffer_chains_only_after_confirmed_provider_post_id(self):
        workflow = source(".github/workflows/buffer-backlog.yml")
        self.assertIn("actions: write", workflow)
        self.assertIn("id: send", workflow)
        self.assertIn("buffer_delivery_gate.py confirm", workflow)
        self.assertIn("if: steps.send.outputs.queued == 'true'", workflow)
        self.assertIn("buffer_delivery_gate.py dispatch", workflow)

    def test_repaired_private_deep_preview_chains_until_restored(self):
        workflow = source(".github/workflows/daily-preview.yml")
        self.assertIn("PRIVATE_DEEP_CAPTION_REVISIONS_PENDING", workflow)
        self.assertIn("eligible_retry(ep,receipt,preview_fingerprint(ep))", workflow)
        self.assertIn("waiting=revised+waiting", workflow)
        self.assertIn('ep["id"] in published', workflow)
        self.assertIn('ep.get("auto_publish") is not False', workflow)

    def test_depleted_buffer_reserve_reports_failure_not_green(self):
        workflow = source(".github/workflows/buffer-backlog.yml")
        self.assertIn("min_queue_reserve = 7", workflow)
        self.assertIn("if len(queued) >= min_queue_reserve:", workflow)
        self.assertIn("BUFFER_RESERVE_UNDER_MINIMUM", workflow)
        self.assertIn("raise SystemExit(1)", workflow)

    def test_no_legacy_scheduled_publisher(self):
        self.assertFalse((ROOT / ".github/workflows/publora-backlog.yml").exists())
        active = (ROOT / ".github/workflows").glob("*.yml")
        for workflow in active:
            body = workflow.read_text(encoding="utf8").lower()
            with self.subTest(workflow=workflow.name):
                self.assertNotIn("publora_autopublish.py", body)
                self.assertNotIn("secrets.publora_api_key", body)

    def test_buffer_does_not_import_legacy_publisher(self):
        script = source("cloud-shorts/buffer_autopublish.py")
        self.assertIn("from publication_safety import", script)
        self.assertNotIn("import publora_autopublish", script)
        self.assertIn("is_motorcycle_episode(episode)", script)

    def test_historical_receipts_remain_for_deduplication(self):
        script = source("cloud-shorts/buffer_autopublish.py")
        self.assertIn('"publication-receipts/"', script)
        self.assertIn('"buffer-publication-receipts/"', script)


if __name__ == "__main__":
    unittest.main()
