"""Cartesia/DEEP routing retains history and forbids publisher fallbacks."""
import unittest
from unittest.mock import patch
import voice_routing as v
import cartesia_voice as c
import deep_voice as d

VOICE = "0f111c12-cabc-4ba0-9a29-1ef98b133e90"


class VoiceRoutingTests(unittest.TestCase):
    def test_no_unapproved_provider_and_legacy_defaults_unchanged(self):
        self.assertEqual(v.new_episode_configuration({}),
                         {"voice_engine":d.VOICE_ENGINE,
                          "voice_profile":d.PROFILE_ID})
        with self.assertRaisesRegex(ValueError,"UNAPPROVED_TTS_PROVIDER"):
            v.new_episode_configuration({"GUSTAVA_TTS_PROVIDER":"silero"})
        with self.assertRaisesRegex(ValueError,"CARTESIA_VOICE_ID_NOT_SET"):
            v.new_episode_configuration({"GUSTAVA_TTS_PROVIDER":c.VOICE_ENGINE})

    def test_approved_cartesia_mode_pins_uuid_to_each_new_episode(self):
        config=v.new_episode_configuration({
            "GUSTAVA_TTS_PROVIDER": c.VOICE_ENGINE,
            "CARTESIA_VOICE_ID":VOICE,
        })
        self.assertEqual(config["voice_engine"],c.VOICE_ENGINE)
        self.assertEqual(config["voice_profile"],c.PROFILE_ID)
        self.assertEqual(config["cartesia_voice_id"],VOICE)

    def test_only_valid_secret_preflight_selects_a_private_cartesia_script(self):
        e=dict(v.new_episode_configuration({
            "GUSTAVA_TTS_PROVIDER":c.VOICE_ENGINE,"CARTESIA_VOICE_ID":VOICE}),
            auto_preview=True,auto_publish=False,narration="Мотоцикл едет.")
        self.assertFalse(v.ready(e,{"CARTESIA_TTS_ENABLED":"1"}))
        self.assertTrue(v.ready(e,{
            "CARTESIA_TTS_ENABLED":"1","CARTESIA_KEY_PRESENT":"true"}))
        self.assertFalse(v.ready(dict(e,auto_publish=True),{
            "CARTESIA_TTS_ENABLED":"1","CARTESIA_KEY_PRESENT":"true"}))
        self.assertEqual(v.expected_profile(e),c.PROFILE_ID)
        self.assertIsNone(v.expected_profile(dict(e,cartesia_voice_id="invalid")))

    def test_legacy_original_deep_receipts_still_work(self):
        ep={"id":"old","voice_engine":d.VOICE_ENGINE}
        with patch("deep_voice.ready",return_value=True):
            self.assertTrue(v.ready(ep))
        report={"voice_qa_passed":True,"mixed_audio_qa_passed":True,
                "voice_profile":d.PROFILE_ID,"male_voice_verified":True}
        self.assertTrue(v.may_publish_with_verified_profile(ep,report))
        report["voice_profile"]=c.PROFILE_ID
        self.assertFalse(v.may_publish_with_verified_profile(ep,report))

    def test_only_exact_matching_cartesia_profile_reaches_release_gate(self):
        ep={"voice_engine":c.VOICE_ENGINE,"voice_profile":c.PROFILE_ID,
            "cartesia_voice_id":VOICE}
        report={"voice_qa_passed":True,"mixed_audio_qa_passed":True,
                "voice_profile":c.PROFILE_ID,"male_voice_verified":True}
        self.assertTrue(v.may_publish_with_verified_profile(ep,report))
        self.assertFalse(v.may_publish_with_verified_profile(
            ep,dict(report,male_voice_verified=False)))
        self.assertFalse(v.may_publish_with_verified_profile(
            ep,dict(report,mixed_audio_qa_passed=False)))


if __name__ == "__main__":
    unittest.main()
