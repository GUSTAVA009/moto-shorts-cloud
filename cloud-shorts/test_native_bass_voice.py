"""Native studio bass baritone: proof must bind correct MIT actor and SHA."""
import tempfile,unittest,wave
from pathlib import Path
from unittest.mock import patch
import native_bass_voice as n
from test_voice_style import generate_synthetic_voice

class RealMaleBassVoiceTests(unittest.TestCase):
    def test_actor_model_and_processing_immutable(self):
        self.assertEqual(n.VOICE_ENGINE,"silero_mit_bass_baritone")
        self.assertEqual(n.SPEAKER,"ru_alexandr")
        self.assertEqual(n.LICENSE_NAME,"MIT")
        self.assertEqual(n.MODEL_ID,"v5_cis_base_nostress")
        self.assertNotIn("rubberband",n.FILTER)
        self.assertNotIn("asoftclip",n.FILTER)
        self.assertNotIn("haas",n.FILTER)
        self.assertIn("loudnorm",n.FILTER)

    def test_missing_actor_proof_must_block(self):
        with tempfile.TemporaryDirectory() as td:
            audio=Path(td)/"n.wav"
            generate_synthetic_voice(audio)
            with self.assertRaisesRegex(ValueError,"missing"):
                n.validate_report(audio)

    def test_untrusted_profile_cannot_be_passed_as_real_actor(self):
        with tempfile.TemporaryDirectory() as td:
            audio=Path(td)/"n.wav"
            generate_synthetic_voice(audio)
            n.profile_report_path(audio).write_text('{"profile_id":"fake","quality_passed":true}',encoding="utf8")
            with self.assertRaises(ValueError):
                n.validate_report(audio)

if __name__=="__main__":
    unittest.main()
