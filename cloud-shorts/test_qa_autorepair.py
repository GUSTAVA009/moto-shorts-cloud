"""Test meaningful automatic voice repairs without downloading audio models."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest

import qa_autorepair as qa


class VoiceAutorepairTests(unittest.TestCase):
    def report(self, ep="test-motorcycle-short", coverage=1.0, passed=True):
        return {"episode_id": ep, "status": "passed" if passed else "manual_review_required",
                "passed": passed, "lexical_coverage": coverage,
                "final_word_present": True, "numerics_match": True,
                "source": "FINAL_MIXED_MP4"}

    def test_passes_only_both_exact_episode_reports(self):
        v = self.report()
        m = self.report()
        self.assertTrue(qa.passes(v, m, "test-motorcycle-short"))
        m["lexical_coverage"] = .94
        self.assertFalse(qa.passes(v, m, "test-motorcycle-short"))
        m["lexical_coverage"] = 1.0
        m["episode_id"] = "other"
        self.assertFalse(qa.passes(v, m, "test-motorcycle-short"))

    def test_success_without_unnecessary_rerender(self):
        called = []
        def runner(episode, work, dist, speed, gain):
            called.append((speed, gain))
            return self.report(), self.report()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(qa, "HERE", Path(tmp)):
                self.assertEqual(qa.repair("test-motorcycle-short", runner=runner), 0)
                audit = json.loads((Path(tmp) / "dist/new/test-motorcycle-short/repair_history.json").read_text())
        self.assertTrue(audit["quality_passed"])
        self.assertEqual(len(called), 1)

    def test_repair_failed_raw_and_mixed_voice_with_conservative_variations(self):
        called = []
        def runner(episode, work, dist, speed, gain):
            called.append((speed, gain))
            if len(called) == 1:
                return self.report(coverage=.92, passed=False), self.report()
            return self.report(), self.report()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(qa, "HERE", Path(tmp)):
                self.assertEqual(qa.repair("test-motorcycle-short", runner=runner), 0)
        self.assertEqual(called, [(1.05, .14), (1.00, .18)])

    def test_all_failed_but_qa_artifact_saved_for_review(self):
        def runner(episode, work, dist, speed, gain):
            return self.report(coverage=.88, passed=False), self.report(coverage=.9, passed=False)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(qa, "HERE", Path(tmp)):
                self.assertEqual(qa.repair("test-motorcycle-short", runner=runner), 0)
                audit = json.loads((Path(tmp) / "dist/new/test-motorcycle-short/repair_history.json").read_text())
        self.assertFalse(audit["quality_passed"])
        self.assertEqual(len(audit["attempts"]), 3)

    def test_technical_source_error_does_not_loop_or_publish(self):
        calls = []
        def runner(episode, work, dist, speed, gain):
            calls.append(1)
            raise RuntimeError("Unlicensed or unavailable footage")
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(qa, "HERE", Path(tmp)):
                self.assertEqual(qa.repair("test-motorcycle-short", runner=runner), 1)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
