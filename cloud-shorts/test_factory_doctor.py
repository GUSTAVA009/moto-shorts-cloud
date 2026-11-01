"""Read-only factory doctor must never claim service/publication success.

Tests execute no network and never access user file paths.
"""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOCTOR = ROOT / "scripts" / "factory_doctor.py"


def load_doctor():
    spec = importlib.util.spec_from_file_location("factory_doctor", DOCTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FactoryDoctorSafetyTests(unittest.TestCase):
    def test_no_configuration_is_not_live_service(self):
        doctor = load_doctor()
        result = doctor.audit(env={})
        self.assertTrue(result["not_proof_of_live_publication"])
        self.assertIsNone(result["production_mp4_verified"])
        self.assertIsNone(result["buffer_scheduled_live"])
        self.assertIsNone(result["buffer_sent_live"])
        self.assertIsNone(result["youtube_public_shorts_verified"])
        self.assertFalse(result["buffer_api_key_configured"])
        self.assertTrue(all(not row["configured"]
                            for row in result["voice_routes"].values()))
        self.assertEqual(result["mode"],"offline_read_only_no_network_calls")

    def test_all_secrets_hidden_and_config_only_never_claims_real_wav(self):
        doctor = load_doctor()
        secret = "gvk_"+"verySensitiveSECRET"*4
        env = {
            "BUFFER_API_KEY": "sensitive_buffer_secret",
            "GUSTAVA_TTS_PROVIDER": "gustava_selfhosted_qwen3",
            "GUSTAVA_SELFHOSTED_TTS_ENABLED": "1",
            "GUSTAVA_VOICE_API_KEY": secret,
            "GUSTAVA_VOICE_API_URL": "https://example.org/v1/audio/speech",
            "GUSTAVA_VOICE_APPROVED_HOST":"example.org",
            "GUSTAVA_VOICE_REFERENCE_SHA256": "a"*64,
        }
        report = doctor.audit(env=env)
        self.assertTrue(report["voice_routes"]["cloud_qwen"]["configured"])
        self.assertIsNone(report["voice_routes"]["cloud_qwen"]["live_wav_verified"])
        self.assertTrue(report["buffer_api_key_configured"])
        serialized=__import__("json").dumps(report)
        self.assertNotIn(secret,serialized)
        self.assertNotIn(env["BUFFER_API_KEY"],serialized)
        self.assertNotIn("example.org",serialized)

    def test_metadata_counts_not_mistaken_for_mp4(self):
        doctor = load_doctor()
        report=doctor.audit(env={})
        self.assertGreater(report["curated_pexels_source_candidates"],30)
        self.assertGreater(report["unused_curated_source_candidates"],0)
        self.assertIsNone(report["production_mp4_verified"])


if __name__=="__main__":
    unittest.main()
