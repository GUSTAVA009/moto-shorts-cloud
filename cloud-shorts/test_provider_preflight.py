"""No-network tests for source/TTS preflight before permanent reservation."""
import io
import urllib.error
import unittest
from provider_preflight import require_available, probe_http


class PreflightTests(unittest.TestCase):
    def test_offline_owner_original_is_not_marked_usable(self):
        episode = {"footage": [{"url":
            "https://84-252-66-87.sslip.io/yt-factory-originals/clip.mp4"}]}
        called = []
        def offline(url, *, voice):
            called.append((url, voice))
            raise RuntimeError("PROVIDER_PREFLIGHT_CONNECTION_ORIGINAL_FOOTAGE")
        with self.assertRaisesRegex(RuntimeError,"CONNECTION_ORIGINAL_FOOTAGE"):
            require_available(episode, probe=offline)
        self.assertEqual(len(called),1)
        self.assertFalse(called[0][1])

    def test_same_owner_clip_checked_once_no_duplicate_network_request(self):
        url="https://84-252-66-87.sslip.io/yt-factory-originals/original.mp4"
        seen=[]
        require_available({"footage":[{"url":url},{"url":url}]},
                          probe=lambda u, *, voice:seen.append((u,voice)))
        self.assertEqual(seen,[(url,False)])

    def test_pexels_does_not_require_unrelated_owner_server(self):
        def unexpected(*args,**kwargs):
            raise AssertionError("No owner/voice preflight required")
        require_available({"footage":[
            {"url":"https://videos.pexels.com/video-files/1/source.mp4"}]},
            probe=unexpected)

    def test_reject_owner_host_unexpected_path(self):
        ep={"footage":[{"url":"https://84-252-66-87.sslip.io/admin"}]}
        with self.assertRaisesRegex(RuntimeError,"UNAPPROVED_OWNER_MEDIA_PATH"):
            require_available(ep)

    def test_approved_cartoon_voice_reachable(self):
        env={
           "GUSTAVA_SELFHOSTED_TTS_ENABLED":"1",
           "GUSTAVA_VOICE_KEY_PRESENT":"true",
           "GUSTAVA_VOICE_API_URL":"https://voice.hapychrust.ru/v1/audio/speech",
           "GUSTAVA_VOICE_APPROVED_HOST":"voice.hapychrust.ru",
           "GUSTAVA_VOICE_REFERENCE_SHA256":"a"*64,
        }
        seen=[]
        ep={"voice_engine":"gustava_selfhosted_qwen3",
            "selfhosted_voice_id":"gustava-cartoon-b-v1","footage":[]}
        require_available(ep,env=env,probe=lambda u, *, voice:seen.append((u,voice)))
        self.assertEqual(seen,[("https://voice.hapychrust.ru/v1/audio/speech",True)])

    def test_voice_unavailable_must_block(self):
        env={
           "GUSTAVA_SELFHOSTED_TTS_ENABLED":"1",
           "GUSTAVA_VOICE_KEY_PRESENT":"true",
           "GUSTAVA_VOICE_API_URL":"https://voice.hapychrust.ru/v1/audio/speech",
           "GUSTAVA_VOICE_APPROVED_HOST":"voice.hapychrust.ru",
           "GUSTAVA_VOICE_REFERENCE_SHA256":"a"*64,
        }
        def down(url, *, voice):
            raise RuntimeError("PROVIDER_PREFLIGHT_HTTP_530_VOICE")
        with self.assertRaisesRegex(RuntimeError,"ALL_VOICE_ROUTES_DOWN.*530"):
            require_available({"voice_engine":"gustava_selfhosted_qwen3",
                               "selfhosted_voice_id":"gustava-cartoon-b-v1"},env=env,probe=down)

    def test_http_error_405_proves_post_only_voice_reachable_not_audio(self):
        def post_only(req, timeout):
            raise urllib.error.HTTPError(req.full_url,405,"Method Not Allowed",{},None)
        probe_http("https://voice.hapychrust.ru/v1/audio/speech",
                   voice=True,opener=post_only)
        with self.assertRaisesRegex(RuntimeError,"HTTP_405_ORIGINAL_FOOTAGE"):
            probe_http("https://84-252-66-87.sslip.io/yt-factory-originals/1.mp4",
                       opener=post_only)

    def test_cloudflare_http_530_does_not_pass(self):
        def down(req, timeout):
            raise urllib.error.HTTPError(req.full_url,530,"Origin Error",{},None)
        with self.assertRaisesRegex(RuntimeError,"HTTP_530_VOICE"):
            probe_http("https://voice.hapychrust.ru/v1/audio/speech",
                       voice=True,opener=down)


if __name__=="__main__":
    unittest.main()
