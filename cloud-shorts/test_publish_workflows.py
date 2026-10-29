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
        self.assertIn("vars.BUFFER_AUTO_PUBLISH_ENABLED == 'true'", workflow)

    def test_daily_generation_never_directly_posts(self):
        workflow = source(".github/workflows/daily-preview.yml").casefold()
        self.assertNotIn("publora", workflow)
        self.assertNotIn("buffer_autopublish.py", workflow)
        self.assertNotIn("publishnow", workflow)
        self.assertIn("upload-artifact@v4", workflow)

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
