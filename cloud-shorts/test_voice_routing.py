"""Owner-approved PRIVATE Qwen route, no SaaS voices and no silent fallback."""
import unittest
from unittest.mock import patch
import voice_routing as r
import deep_voice as d
import selfhosted_voice as h


class VoiceRoutingTests(unittest.TestCase):
    def test_unattended_qwen_default_and_immutable_historic_deep(self):
        # A missing/blank variable must NEVER silently queue paid/manual Deep.
        self.assertEqual(r.new_episode_configuration({}),
                         {"voice_engine":h.VOICE_ENGINE,
                          "voice_profile":h.PROFILE_ID,
                          "selfhosted_voice_id":h.VOICE_ID})
        self.assertEqual(r.new_episode_configuration({"GUSTAVA_TTS_PROVIDER":""}),
                         r.new_episode_configuration({}))
        # Historical DEEP is only enabled by an explicit opt-in or existing episode.
        self.assertEqual(r.new_episode_configuration(
            {"GUSTAVA_TTS_PROVIDER":d.VOICE_ENGINE}),
            {"voice_engine":d.VOICE_ENGINE,"voice_profile":d.PROFILE_ID})
        with patch("deep_voice.ready",return_value=True):
            self.assertTrue(r.ready({"voice_engine":d.VOICE_ENGINE}))
        receipt={"voice_qa_passed":True,"mixed_audio_qa_passed":True,
                 "male_voice_verified":True,"voice_profile":d.PROFILE_ID}
        self.assertTrue(r.may_publish_with_verified_profile(
            {"voice_engine":d.VOICE_ENGINE},receipt))

    def test_cloud_cpu_is_explicit_single_channel_speaker(self):
        cfg=r.new_episode_configuration({"GUSTAVA_TTS_PROVIDER":h.VOICE_ENGINE})
        self.assertEqual(cfg,{"voice_engine":h.VOICE_ENGINE,
                              "voice_profile":h.PROFILE_ID,
                              "selfhosted_voice_id":h.VOICE_ID})
        self.assertEqual(r.expected_profile(cfg),h.PROFILE_ID)
        self.assertIsNone(r.expected_profile(dict(cfg,selfhosted_voice_id="other")))

    def test_only_secure_owner_domain_and_key_enables_private_preview(self):
        ep=dict(r.new_episode_configuration({"GUSTAVA_TTS_PROVIDER":h.VOICE_ENGINE}),
                auto_preview=True,auto_publish=False)
        env={"GUSTAVA_SELFHOSTED_TTS_ENABLED":"1",
             "GUSTAVA_VOICE_KEY_PRESENT":"true",
             "GUSTAVA_VOICE_API_URL":"https://voice.hapychrust.ru/v1/audio/speech",
             "GUSTAVA_VOICE_APPROVED_HOST":"voice.hapychrust.ru",
             "GUSTAVA_VOICE_REFERENCE_SHA256":"a"*64}
        self.assertTrue(r.ready(ep,env))
        self.assertFalse(r.ready(ep,dict(env,GUSTAVA_VOICE_KEY_PRESENT="false")))
        self.assertFalse(r.ready(ep,dict(env,GUSTAVA_VOICE_API_URL=
            "https://random-tts.example/v1/audio/speech")))
        self.assertFalse(r.ready(dict(ep,auto_publish=True),env))
        self.assertFalse(r.ready(ep,dict(env,GUSTAVA_VOICE_REFERENCE_SHA256="nope")))

    def test_all_external_paid_voice_engines_are_rejected(self):
        for forbidden in ("cartesia_sonic36","silero","kokoro","unknown","openvoice"):
            with self.subTest(forbidden=forbidden):
                with self.assertRaisesRegex(ValueError,"UNAPPROVED_TTS_PROVIDER"):
                    r.new_episode_configuration({"GUSTAVA_TTS_PROVIDER":forbidden})
                self.assertFalse(r.ready({"voice_engine":forbidden}))
                self.assertIsNone(r.expected_profile({"voice_engine":forbidden}))

    def test_only_independently_qa_verified_original_profile_reaches_release(self):
        ep=dict(r.new_episode_configuration({"GUSTAVA_TTS_PROVIDER":h.VOICE_ENGINE}))
        receipt={"voice_qa_passed":True,"mixed_audio_qa_passed":True,
                 "male_voice_verified":True,"voice_profile":h.PROFILE_ID}
        self.assertTrue(r.may_publish_with_verified_profile(ep,receipt))
        for bad in (
            dict(receipt,mixed_audio_qa_passed=False),
            dict(receipt,voice_profile="unverified"),
            dict(receipt,male_voice_verified=False)
        ):
            self.assertFalse(r.may_publish_with_verified_profile(ep,bad))


if __name__ == "__main__":
    unittest.main()
