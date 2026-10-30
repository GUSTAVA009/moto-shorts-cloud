import hashlib
import unittest
from deep_voice import approved_asset, VOICE_ENGINE, PROFILE_ID, digest

TEXT="Наш глубокий голос для оригинального мотосценария."
AUDIO={
    "provider":"aidocmaker.com",
    "voice_id":"deep",
    "transcript_sha256":hashlib.sha256(TEXT.encode("utf-8")).hexdigest(),
    "preview_url":"https://storage.googleapis.com/adm--audio-playback--7d--public/mcp-preview/59b382df-d33f-45d2-943d-22f1db747299.mp3"
}

class RealDeepPolicyTests(unittest.TestCase):
    def test_only_exact_provider_deep_voice(self):
        self.assertEqual(VOICE_ENGINE,"aidocmaker_deep")
        self.assertEqual(PROFILE_ID,"gustava_create_audio_deep_v1")
        self.assertEqual(approved_asset(AUDIO,TEXT),AUDIO["preview_url"])
    def test_no_matching_text_no_reusing_old_preset(self):
        for changed in (dict(AUDIO,voice_id="roman"),
                        dict(AUDIO,provider="unknown"),
                        dict(AUDIO,preview_url="https://fake.example/test.mp3"),
                        dict(AUDIO,preview_url="https://storage.googleapis.com.evil.test/mcp-preview/a.mp3")):
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    approved_asset(changed,TEXT)
        with self.assertRaises(ValueError):
            approved_asset(AUDIO,"One changed word")
        with self.assertRaises(ValueError):
            approved_asset(None,TEXT)
    def test_known_asset_hash(self):
        self.assertEqual(digest(b"abc"),hashlib.sha256(b"abc").hexdigest())

if __name__=="__main__":
    unittest.main()
