"""Regression check: both autopublish callers must pass final-mix QA as one shell command."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = [
    ".github/workflows/daily-preview.yml",
    ".github/workflows/publora-backlog.yml",
]

class PublisherShellTests(unittest.TestCase):
    def test_mixed_qa_in_same_command(self):
        for relative in WORKFLOWS:
            script = (ROOT / relative).read_text(encoding="utf8")
            with self.subTest(workflow=relative):
                self.assertIn("--voice-qa ", script)
                self.assertIn("--mixed-qa ", script)
                self.assertRegex(script, r'--voice-qa[^\n]*\\\s*\n\s*--mixed-qa')
                self.assertIn("publora_autopublish.py", script)

if __name__ == "__main__":
    unittest.main()
