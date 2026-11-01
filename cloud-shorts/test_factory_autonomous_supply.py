"""Factory, not ChatGPT: unattended voice + source + MP4 dispatch contract.

Tests are offline. Do not credit scripts or provider configs as finished
WAVs, generated MP4s, queued Buffer posts or verified public YouTube Shorts.
"""
import unittest
from unittest.mock import patch
import autofill_catalog as supplier
import voice_routing
import selfhosted_voice
import rolling_batch_worker as watcher
from production_readiness import inventory, production_unavailable
from pathlib import Path


def qwen_episode(slug="new-script"):
    return dict(id=slug, auto_preview=True, auto_publish=False,
                voice_engine=selfhosted_voice.VOICE_ENGINE,
                voice_profile=selfhosted_voice.PROFILE_ID,
                selfhosted_voice_id=selfhosted_voice.VOICE_ID)


class FactoryAutonomousSupplyTests(unittest.TestCase):
    def test_new_episode_never_defaults_to_manual_deep(self):
        cfg = voice_routing.new_episode_configuration({})
        self.assertEqual(cfg["voice_engine"],selfhosted_voice.VOICE_ENGINE)
        self.assertEqual(cfg["selfhosted_voice_id"],selfhosted_voice.VOICE_ID)
        self.assertNotIn("deep_audio",cfg)

    def test_legacy_unvoiced_deep_does_not_deadlock_unattended_production(self):
        bad=[dict(id="old-"+str(i),auto_preview=True,auto_publish=True,
                  voice_engine="aidocmaker_deep") for i in range(15)]
        catalog={"episodes":bad}
        self.assertEqual(supplier.pending_originals(catalog,set()),15)
        self.assertEqual(supplier.pending_originals(
            catalog,set(),autonomous=True),0)
        self.assertFalse(supplier.actionable_voice_plan(bad[0]))
        catalog["episodes"].append(qwen_episode())
        self.assertEqual(supplier.pending_originals(
            catalog,set(),autonomous=True),1)
        self.assertEqual(supplier.pending_originals(
            catalog,{"new-script"},autonomous=True),0)

    def test_legacy_deep_can_only_enter_when_sha_pinned_recorded(self):
        episode=dict(id="legacy",auto_preview=True,auto_publish=True,
                     voice_engine="aidocmaker_deep")
        with patch("autofill_catalog.approved_legacy_deep",return_value=False):
            self.assertFalse(supplier.actionable_voice_plan(episode))
        with patch("autofill_catalog.approved_legacy_deep",return_value=True):
            self.assertTrue(supplier.actionable_voice_plan(episode))

    def test_cloud_local_and_third_configured_not_an_actual_wav(self):
        ep=qwen_episode()
        config={
            "GUSTAVA_VOICE_REFERENCE_SHA256":"a"*64,
            "GUSTAVA_LOCAL_TTS_ENABLED":"1",
            "GUSTAVA_LOCAL_VOICE_API_URL":
                "https://pc-voice.hapychrust.ru/v1/audio/speech",
            "GUSTAVA_LOCAL_VOICE_APPROVED_HOST":"pc-voice.hapychrust.ru",
            "GUSTAVA_LOCAL_VOICE_KEY_PRESENT":"true",
        }
        waiting={"episodes":[ep]}
        gone=inventory(waiting,set(),environment={})
        self.assertTrue(production_unavailable(gone))
        self.assertEqual(gone["configured_voice_route_names"],[])
        configured=inventory(waiting,set(),environment=config)
        self.assertFalse(production_unavailable(configured))
        self.assertEqual(configured["ready_unattended_voice_episodes"],1)
        self.assertEqual(configured["configured_voice_route_names"],["local_pc"])
        self.assertFalse(configured["voice_route_reachability_verified"])
        self.assertEqual(inventory(waiting,{"new-script"},environment=config)
                         ["ready_unattended_voice_episodes"],0)

    def test_low_queue_drives_actions_not_fake_posts(self):
        plan=watcher.dispatch_plan(True,True,[],0,0,0)
        self.assertTrue(plan["request_new_sources"])
        self.assertTrue(plan["voice_not_ready"])
        self.assertTrue(plan["no_qa_mp4_for_buffer"])
        self.assertFalse(plan["request_voice_and_render"])
        self.assertFalse(plan["request_verified_buffer_delivery"])
        warmed=watcher.dispatch_plan(True,True,[],1,1,0)
        self.assertTrue(warmed["request_voice_and_render"])
        self.assertFalse(warmed["request_verified_buffer_delivery"])
        ready=watcher.dispatch_plan(True,True,[],1,2,1)
        self.assertTrue(ready["request_voice_and_render"])
        self.assertTrue(ready["request_verified_buffer_delivery"])
        idle=watcher.dispatch_plan(False,False,[],10,4,0)
        self.assertFalse(idle["request_new_sources"])
        self.assertFalse(idle["request_voice_and_render"])
        self.assertFalse(idle["request_verified_buffer_delivery"])
        self.assertFalse(idle["voice_not_ready"])
        for count in (-1,):
            with self.assertRaises(ValueError):
                watcher.dispatch_plan(True,False,[],count,0,0)

    def test_real_actions_receive_provisioning_and_never_auto_pick_manual_deep(self):
        repo=Path(__file__).resolve().parents[1]
        source=(repo/".github/workflows/autofill-motorcycle.yml").read_text("utf8")
        roll=(repo/".github/workflows/rolling-ten.yml").read_text("utf8")
        self.assertIn("GUSTAVA_TTS_PROVIDER: gustava_selfhosted_qwen3",source)
        for k in ("GUSTAVA_VOICE_REFERENCE_SHA256",
                  "GUSTAVA_SELFHOSTED_TTS_ENABLED",
                  "GUSTAVA_LOCAL_VOICE_KEY_PRESENT",
                  "GUSTAVA_TERTIARY_VOICE_KEY_PRESENT"):
            self.assertIn(k,source)
            self.assertIn(k,roll)
        self.assertNotIn("voice_id='silero'",source)
        self.assertNotIn("pitch_shifted_substitute",source)


if __name__=="__main__":
    unittest.main()
