"""Owner-approved factory contract. No network, no publication, no provider credits.

This is a regression test, NOT a claim that 10 videos were published or that
autonomous voice synthesis is connected. Tests block accidental loss of the
rules when ChatGPT, Claude Code or another agent starts in a fresh chat.
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / "cloud-shorts"
CONTRACT = json.loads((HERE / "factory_contract.json").read_text(encoding="utf8"))


class FactoryContractTests(unittest.TestCase):
    def test_identity_preserves_the_exact_channel_and_keeps_projects_separate(self):
        self.assertEqual(CONTRACT["project"]["channel_id"], "UCS0QCodPcFBTjMt4ioEWOUw")
        self.assertEqual(CONTRACT["project"]["handle"], "@gustava009")
        self.assertEqual(CONTRACT["project"]["separate_other_channel"], "@motobratr1")
        workflow = (ROOT / ".github/workflows/buffer-backlog.yml").read_text(encoding="utf8")
        self.assertIn(CONTRACT["project"]["channel_id"], workflow)
        self.assertNotIn("@motobratr1", workflow.lower())

    def test_factory_is_exactly_the_owner_approved_deep_not_an_alternative(self):
        import deep_voice
        self.assertEqual(deep_voice.VOICE_ENGINE, CONTRACT["voice"]["voice_engine"])
        self.assertEqual(deep_voice.VOICE_ID, CONTRACT["voice"]["voice_id"])
        self.assertEqual(deep_voice.PROFILE_ID, CONTRACT["voice"]["voice_profile"])
        self.assertFalse(CONTRACT["voice"]["allow_fallback"])
        self.assertTrue(CONTRACT["voice"]["requires_sha_pinned_original"])
        wf = (ROOT / ".github/workflows/daily-preview.yml").read_text(encoding="utf8")
        self.assertIn("PRODUCTION_GUSTAVA_REAL_CREATE_AUDIO_DEEP_ONLY", wf)
        self.assertIn("faster-whisper", wf)
        for line in wf.splitlines():
            if "pip install" in line and "python3" in line:
                for forbidden in ("piper-tts", "silero==", "kokoro=="):
                    self.assertNotIn(forbidden, line.lower())

    def test_daily_targets_and_actual_queue_limits_remain_distinct(self):
        import ten_daily_slots as s
        import rolling_batch_worker as w
        from rolling_batches import BATCH_SIZE
        p = CONTRACT["production"]
        b = CONTRACT["buffer"]
        self.assertEqual(p["target_new_unique_shorts_per_day"], 10)
        self.assertEqual(p["reviewed_mp4_reserve_target"], 10)
        self.assertTrue(p["never_count_script_as_mp4"])
        self.assertEqual(b["provider"], "Buffer")
        self.assertEqual(b["target_scheduled_posts"], 10)
        self.assertEqual(b["free_tier_scheduled_limit"], 10)
        self.assertEqual(b["replenish_at_or_below_scheduled"], 9)
        self.assertEqual(b["hard_low_queue_warning_at"], w.MIN_BUFFER_SCHEDULED)
        self.assertEqual(w.REFILL_AT_OR_BELOW_SCHEDULED, 9)
        self.assertEqual(BATCH_SIZE, 10)
        self.assertEqual(s.MAX_POSTS_PER_DAY, 10)
        self.assertEqual(s.TARGET_PER_DAY, 16)  # 90-minute windows != 16 posts
        minutes = [h * 60 + m for h, m in s.LOCAL_TIMES]
        self.assertTrue(all(b - a == CONTRACT["publishing"]["spacing_minutes"]
                            for a, b in zip(minutes, minutes[1:])))

    def test_story_bank_is_not_video_supply_and_retains_original_mix(self):
        from story_reserve import RESERVE_CAPACITY
        self.assertGreaterEqual(RESERVE_CAPACITY,
                                CONTRACT["production"]["script_reserve_minimum"])
        batch = json.loads(
            (HERE / "production_batch20_20261030.json").read_text(encoding="utf8")
        )
        self.assertEqual(batch["channel_id"], CONTRACT["project"]["channel_id"])
        self.assertEqual(batch["voice_engine"], CONTRACT["voice"]["voice_engine"])
        self.assertEqual(batch["voice_id"], CONTRACT["voice"]["voice_id"])
        self.assertEqual(batch["target_total"], CONTRACT["editorial"]["batch_size"])
        self.assertEqual(batch["working_mix"], CONTRACT["editorial"]["batch_20_counts"])
        self.assertEqual(sum(CONTRACT["editorial"]["category_percent"].values()), 100)
        for kind, qty in batch["working_mix"].items():
            self.assertEqual(CONTRACT["editorial"]["category_percent"][kind],
                             qty * 100 // 20)

    def test_production_contract_keeps_known_provider_gap_visible(self):
        from production_readiness import inventory
        report = inventory({"episodes":[]}, [])
        # Never label a story bank as an independently synthesized DEEP voice.
        self.assertEqual(report["unrendered_verified_deep_originals"], 0)
        self.assertFalse(report["has_autonomous_deep_tts"])
        self.assertTrue(CONTRACT["buffer"]["confirm_real_post_id"])
        self.assertTrue(CONTRACT["buffer"]["never_retry_uncertain_upload"])

    def test_owner_approved_cartesia_api_not_auto_charged_or_published(self):
        from cartesia_voice import VOICE_ENGINE, MODEL_ID, PROFILE_ID
        change = CONTRACT["owner_approved_voice_automation_change"]
        cartesia = CONTRACT["cartesia_voice"]
        self.assertEqual(change["date"], "2026-11-01")
        self.assertTrue(change["existing_deep_remains_unmodified"])
        self.assertTrue(change["no_unapproved_billing"])
        self.assertEqual(cartesia["voice_engine"], VOICE_ENGINE)
        self.assertEqual(cartesia["voice_profile"], PROFILE_ID)
        self.assertEqual(cartesia["model_id"], MODEL_ID)
        self.assertTrue(cartesia["requires_explicit_activation"])
        self.assertTrue(cartesia["requires_monthly_budget"])
        self.assertTrue(cartesia["requires_commercial_plan_for_publication"])
        self.assertFalse(CONTRACT["voice"]["allow_fallback"])
        wf = (ROOT / ".github/workflows/daily-preview.yml").read_text("utf8")
        self.assertIn("CARTESIA_API_KEY: ${{ secrets.CARTESIA_API_KEY }}", wf)
        self.assertIn("CARTESIA_TTS_ENABLED: ${{ vars.CARTESIA_TTS_ENABLED }}", wf)
        self.assertIn("test_cartesia_voice.py", wf)
        producer = (ROOT / ".github/workflows/autofill-motorcycle.yml").read_text("utf8")
        self.assertIn("GUSTAVA_TTS_PROVIDER: ${{ vars.GUSTAVA_TTS_PROVIDER }}", producer)
        pub = (ROOT / ".github/workflows/buffer-backlog.yml").read_text("utf8")
        self.assertIn("CARTESIA_COMMERCIAL_PLAN_CONFIRMED", pub)

    def test_no_green_build_can_be_called_public_success(self):
        self.assertTrue(CONTRACT["publishing"]["do_not_mark_success_from_workflow_only"])
        self.assertTrue(CONTRACT["publishing"]["public_release_only_after_individual_visual_review"])
        stages = CONTRACT["evidence_stages"]
        self.assertLess(stages.index("mp4_rendered"), stages.index("visual_qa_passed"))
        self.assertLess(stages.index("visual_qa_passed"), stages.index("human_frame_review_passed"))
        self.assertLess(stages.index("human_frame_review_passed"), stages.index("buffer_post_id_confirmed"))
        self.assertLess(stages.index("buffer_post_id_confirmed"), stages.index("youtube_public_url_confirmed"))
        publisher = (ROOT / ".github/workflows/buffer-backlog.yml").read_text(encoding="utf8")
        self.assertIn("buffer_delivery_gate.py confirm", publisher)
        self.assertIn("find_pending_buffer.py", publisher)

    def test_agents_must_get_the_canonical_rules_instead_of_drifting(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf8")
        instructions = (ROOT / "docs/FACTORY_CONTRACT_RU.md").read_text(encoding="utf8")
        for name in ("docs/FACTORY_CONTRACT_RU.md", "cloud-shorts/factory_contract.json"):
            self.assertIn(name, agents)
        self.assertIn("35%", instructions)
        self.assertIn("25%", instructions)
        self.assertIn("15%", instructions)
        self.assertIn("48", instructions)
        self.assertIn("GUSTAVA DEEP", agents)
        self.assertIn("@motobratr1", agents)

    def test_active_readme_and_setup_do_not_claim_a_rejected_speaker(self):
        readme = (ROOT / "README.md").read_text(encoding="utf8")
        setup = (ROOT / "AUTOPILOT_SETUP_RU.md").read_text(encoding="utf8")
        for body in (readme, setup):
            self.assertIn("aidocmaker_deep", body)
            self.assertIn("voice_id", body)
            self.assertIn("FACTORY_CONTRACT_RU.md", body)
            self.assertNotIn("голосом "+chr(96)+"kokoro_ru_dima"+chr(96), body)
            self.assertNotIn("голосом Kokoro-RU", body)
            self.assertNotIn("до трёх попыток", body)


if __name__ == "__main__":
    unittest.main()
