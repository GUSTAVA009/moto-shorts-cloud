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
        self.assertEqual(called, [(1.00, .12), (1.00, .08)])

    def test_all_failed_but_qa_artifact_saved_for_review(self):
        def runner(episode, work, dist, speed, gain):
            return self.report(coverage=.88, passed=False), self.report(coverage=.9, passed=False)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(qa, "HERE", Path(tmp)):
                self.assertEqual(qa.repair("test-motorcycle-short", runner=runner), 0)
                audit = json.loads((Path(tmp) / "dist/new/test-motorcycle-short/repair_history.json").read_text())
        self.assertFalse(audit["quality_passed"])
        self.assertGreater(len(audit["attempts"]), 3)
        self.assertEqual(len(audit["attempts"]),len(qa.PROFILES))
        self.assertEqual(len({(x["speech_speed"],x["music_gain"])
                              for x in audit["attempts"]}),len(qa.PROFILES))

    def test_stable_real_raw_asr_error_stops_after_new_speech_speed(self):
        called=[]
        def runner(episode, work, dist, speed, gain):
            called.append((speed,gain))
            v=self.report(coverage=.957,passed=False)
            m=self.report(coverage=.957,passed=False)
            v["recognized_text"]="Мотоцикл в потоки машин"
            m["recognized_text"]="Мотоцикл в потоки машин"
            return v,m
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(qa,"HERE",Path(tmp)):
                self.assertEqual(qa.repair("test-motorcycle-short",runner=runner),0)
                audit=json.loads((Path(tmp)/"dist/new/test-motorcycle-short/repair_history.json").read_text())
        self.assertFalse(audit["quality_passed"])
        self.assertEqual(len(called),3)
        self.assertEqual(audit["attempts"][-1]["stopped_reason"],
                         "SAME_FAILED_SOURCE_ASR_AFTER_DIFFERENT_SPEED")

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
