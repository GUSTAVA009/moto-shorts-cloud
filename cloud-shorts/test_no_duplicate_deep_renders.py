"""Prevent re-rendering approved original GUSTAVA DEEP narration for a mere code change."""
import unittest
import preview_queue as q


class DeepPreviewDedupTests(unittest.TestCase):
    def episode(self, source="b"):
        return {
            "id": "moto-rain-example",
            "auto_preview": True,
            "auto_publish": False,
            "voice_engine": "aidocmaker_deep",
            "voice_profile": "gustava_create_audio_deep_v1",
            "voice_revision_requested": True,
            "deep_audio": {"source_audio_sha256": source * 64},
        }

    def receipt(self, source="a"):
        return {
            "id": "moto-rain-example",
            "state": "preview_ready",
            "attempt_count": 1,
            "preview_fingerprint": "old-render",
            "voice_profile": "gustava_create_audio_deep_v1",
            "voice_qa_passed": True,
            "mixed_audio_qa_passed": True,
            "deep_source_sha256": source * 64,
        }

    def test_master_code_change_does_not_rerender_same_audio(self):
        ep = self.episode("a")
        self.assertFalse(q.eligible_retry(ep, self.receipt("a"), "new-code-master"))

    def test_legacy_receipt_without_audio_proof_fails_closed(self):
        receipt = self.receipt()
        receipt.pop("deep_source_sha256")
        self.assertFalse(q.eligible_retry(self.episode(), receipt, "new-code-master"))

    def test_explicit_new_original_deep_mp3_may_rerender_unpublished(self):
        self.assertTrue(q.eligible_retry(self.episode(), self.receipt(), "new-voice-file"))
        changed = self.episode()
        changed["auto_publish"] = True
        self.assertFalse(q.eligible_retry(changed, self.receipt(), "new-voice-file"))

    def test_invalid_hash_cannot_trigger_rerender(self):
        ep = self.episode("x")
        self.assertFalse(q.eligible_retry(ep, self.receipt(), "new-code"))
        receipt = self.receipt()
        receipt["deep_source_sha256"] = "bad"
        self.assertFalse(q.eligible_retry(self.episode(), receipt, "new-code"))

    def test_exhausted_preview_attempts_cannot_rerender(self):
        receipt = self.receipt()
        receipt["attempt_count"] = q.MAX_ATTEMPTS
        self.assertFalse(q.eligible_retry(self.episode(), receipt, "new-source"))

    def test_without_voice_revision_no_rerender(self):
        ep = self.episode()
        ep["voice_revision_requested"] = False
        self.assertFalse(q.eligible_retry(ep, self.receipt(), "changed-code"))



class ConfirmedCityDurationRetryTests(unittest.TestCase):
    def episode(self):
        from pathlib import Path
        import json
        catalog = json.loads((Path(__file__).parent / "episodes.json").read_text("utf8"))
        return next(e for e in catalog["episodes"]
                    if e["id"] == "moto-city-contrast-deep-20261030")

    def reservation(self):
        return {
            "id": "moto-city-contrast-deep-20261030",
            "state": "reserved",
            "run_id": "41045277757",
            "attempt_count": 1,
            "preview_fingerprint": "prior-failed-duration",
        }

    def test_confirmed_failed_private_preview_can_retry_once(self):
        # The earlier private repair has now been completed AND exact visual
        # and 100%-ASR MP4 approved. Never retry the actual released asset.
        approved=self.episode()
        self.assertTrue(approved["auto_publish"])
        self.assertEqual(approved["reviewed_mp4_sha256"],
                         "0ce509c6394ea45a2ce84b8722466c12603e259bcdce029fa0ae2e9138b7f7c0")
        r = self.reservation()
        self.assertFalse(q.eligible_abandoned_visual_duration_retry(
            approved,r,"fixed-real-moving-scenes","failure"))
        # Historical pre-approval transition remains testable without
        # converting the published episode back to private in main.
        ep = dict(approved,auto_publish=False)
        self.assertTrue(q.eligible_abandoned_visual_duration_retry(
            ep, r, "fixed-real-moving-scenes", "failure"))
        self.assertFalse(q.eligible_abandoned_visual_duration_retry(
            ep, r, "fixed-real-moving-scenes", "in_progress"))
        self.assertFalse(q.eligible_abandoned_visual_duration_retry(
            ep, r, "prior-failed-duration", "failure"))
        ep["auto_publish"] = True
        self.assertFalse(q.eligible_abandoned_visual_duration_retry(
            ep, r, "fixed-real-moving-scenes", "failure"))

    def test_no_blind_second_retry_on_unknown_failure(self):
        ep = self.episode()
        receipt = self.reservation()
        receipt["attempt_count"] = q.MAX_ATTEMPTS
        self.assertFalse(q.eligible_abandoned_visual_duration_retry(
            ep, receipt, "new-video", "failure"))
        receipt["attempt_count"] = 1
        ep["visual_duration_revision_reason"] = "unknown"
        self.assertFalse(q.eligible_abandoned_visual_duration_retry(
            ep, receipt, "new-video", "failure"))

    def test_two_actual_ride_scenes_cover_approved_voice_without_padding(self):
        from visual_director import directed_plan, scene_duration_limit
        ep = self.episode()
        lengths = {s["key"]: float(s["duration"]) for s in ep["footage"]}
        plan = directed_plan(ep, lengths, 15.84 + 1.25)
        self.assertEqual(len(plan), 2)
        self.assertEqual(len({x["source"] for x in plan}), 2)
        self.assertGreaterEqual(sum(x["seconds"] for x in plan), 16.97)
        self.assertTrue(all(3.3 <= x["seconds"] <= 9.5 for x in plan))
        self.assertEqual(scene_duration_limit(ep, ep["footage"][0]), 9.5)
        wrong = dict(ep, active_ride_scene_seconds=8.0)
        with self.assertRaisesRegex(RuntimeError, "VISUAL_DURATION_SHORTAGE"):
            directed_plan(wrong, lengths, 15.84 + 1.25)

if __name__ == "__main__":
    unittest.main()
