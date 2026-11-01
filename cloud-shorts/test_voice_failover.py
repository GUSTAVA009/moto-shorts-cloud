"""Offline safety tests for independently hosted cloud/Windows/Chatterbox."""
import hashlib
import json
import unittest
import urllib.error
from unittest.mock import Mock

import voice_failover as v

def env():
    return {
        "GUSTAVA_VOICE_REFERENCE_SHA256": "a" * 64,
        "GUSTAVA_SELFHOSTED_TTS_ENABLED": "1",
        "GUSTAVA_VOICE_API_URL": "https://voice.hapychrust.ru/v1/audio/speech",
        "GUSTAVA_VOICE_APPROVED_HOST": "voice.hapychrust.ru",
        "GUSTAVA_VOICE_API_KEY": "gvk_" + "1" * 48,
        "GUSTAVA_LOCAL_TTS_ENABLED": "1",
        "GUSTAVA_LOCAL_VOICE_API_URL": "https://pc-voice.hapychrust.ru/v1/audio/speech",
        "GUSTAVA_LOCAL_VOICE_APPROVED_HOST": "pc-voice.hapychrust.ru",
        "GUSTAVA_LOCAL_VOICE_API_KEY": "gvk_" + "2" * 48,
        "GUSTAVA_TERTIARY_TTS_ENABLED": "1",
        "GUSTAVA_TERTIARY_VOICE_API_URL": "https://backup-voice.hapychrust.ru/v1/audio/speech",
        "GUSTAVA_TERTIARY_VOICE_APPROVED_HOST": "backup-voice.hapychrust.ru",
        "GUSTAVA_TERTIARY_VOICE_API_KEY": "gvk_" + "3" * 48,
        "GUSTAVA_TERTIARY_VOICE_CANARY_APPROVED": "1",
    }

EPISODE={"id": "moto-test-voice-101", "narration": "Это тест оригинального голоса."}

class VoiceFailoverTests(unittest.TestCase):
    def test_order_and_separate_keys_and_domains(self):
        rows=v.available_routes(env(), require_secret=True)
        self.assertEqual([r.name for r in rows], ["cloud","local_pc","chatterbox_v3"])
        self.assertEqual(len({r.url for r in rows}),3)
        self.assertEqual(len({r.key for r in rows}),3)
        self.assertEqual(rows[-1].expected_backend,"chatterbox_multilingual_v3")

    def test_failover_after_both_sources_unavailable(self):
        seen=[]
        def transport(route, episode, environment):
            seen.append(route.name)
            if route.name in ("cloud", "local_pc"):
                raise v.ProviderUnavailable("network down")
            return (b"VALID",environment["GUSTAVA_VOICE_REFERENCE_SHA256"],route.name)
        result=v.synthesize(EPISODE,env=env(),transport=transport,
                            validator=lambda audio:self.assertEqual(audio,b"VALID"))
        self.assertEqual(result[2],"chatterbox_v3")
        self.assertEqual(seen,["cloud","local_pc","chatterbox_v3"])

    def test_do_not_switch_after_auth_error_or_speaker_mismatch(self):
        for error in (RuntimeError("TTS_REJECTED_cloud_401"),
                      ValueError("OWNER_VOICE_IDENTITY_OR_AUDIO_SHA_REJECTED")):
            seen=[]
            def blocked(route, episode, environment):
                seen.append(route.name)
                raise error
            with self.subTest(error=str(error)),self.assertRaises(type(error)):
                v.synthesize(EPISODE,env=env(),transport=blocked)
            self.assertEqual(seen,["cloud"])

    def test_missing_canary_or_token_does_not_count_as_backup(self):
        state=env()
        state["GUSTAVA_TERTIARY_VOICE_CANARY_APPROVED"]="0"
        self.assertEqual(len(v.available_routes(state)),2)
        state["GUSTAVA_TERTIARY_VOICE_CANARY_APPROVED"]="1"
        state["GUSTAVA_TERTIARY_VOICE_API_KEY"]=""
        self.assertEqual(len(v.available_routes(state,require_secret=True)),2)
        state["GUSTAVA_TERTIARY_VOICE_KEY_PRESENT"]="true"
        self.assertEqual(len(v.available_routes(state,require_secret=False)),3)

    def test_no_web_redirect_ssrf_credentials_or_duplicate_host(self):
        state=env()
        bad=["http://backup-voice.hapychrust.ru/v1/audio/speech",
             "https://backup-voice.hapychrust.ru.evil.com/v1/audio/speech",
             "https://token@backup-voice.hapychrust.ru/v1/audio/speech",
             "https://backup-voice.hapychrust.ru:8443/v1/audio/speech",
             "https://127.0.0.1/v1/audio/speech",
             "https://backup-voice.hapychrust.ru/v1/audio/speech?redirect=1",
             "https://backup-voice.hapychrust.ru/"]
        for u in bad:
            with self.subTest(u=u),self.assertRaises(ValueError):
                v.approved_endpoint(u,state["GUSTAVA_TERTIARY_VOICE_APPROVED_HOST"])
        state["GUSTAVA_LOCAL_VOICE_API_URL"]=state["GUSTAVA_VOICE_API_URL"]
        state["GUSTAVA_LOCAL_VOICE_APPROVED_HOST"]=state["GUSTAVA_VOICE_APPROVED_HOST"]
        self.assertEqual(len(v.available_routes(state)),2)

    def test_only_transient_http_failure_can_be_recovered(self):
        state=env()
        route=v.available_routes(state,require_secret=True)[0]
        class FakeOpener:
            def __init__(self,code): self.code=code
            def open(self,*args,**kwargs):
                raise urllib.error.HTTPError(route.url,self.code,"test",{},None)
        with self.assertRaises(v.ProviderUnavailable):
            v._post(route,EPISODE,state,opener=FakeOpener(503))
        with self.assertRaisesRegex(RuntimeError,"TTS_REJECTED_cloud_401"):
            v._post(route,EPISODE,state,opener=FakeOpener(401))

    def test_responding_speaker_must_match_pinned_identity_and_sha(self):
        state=env()
        route=v.available_routes(state,require_secret=True)[0]
        raw=b"RIFF" + b"test-audio"
        class Response:
            def __init__(self):
                self.headers={
                    "X-Audio-SHA256":hashlib.sha256(raw).hexdigest(),
                    "X-Reference-SHA256":state["GUSTAVA_VOICE_REFERENCE_SHA256"],
                    "X-Voice-ID":v.VOICE_ID,
                    "X-Channel-ID":v.CHANNEL_SLUG,
                }
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def geturl(self):return route.url
            def read(self,n):return raw
        class FakeOpener:
            def open(self,req,timeout):
                self.request=json.loads(req.data)
                return Response()
        opener=FakeOpener()
        self.assertEqual(v._post(route,EPISODE,state,opener=opener)[0],raw)
        self.assertEqual(opener.request["channel_slug"],"gustava")
        class WrongOpener(FakeOpener):
            def open(self,req,timeout):
                response=Response()
                response.headers["X-Voice-ID"]="other-voice"
                return response
        with self.assertRaisesRegex(ValueError,"IDENTITY"):
            v._post(route,EPISODE,state,opener=WrongOpener())

    def test_all_outages_do_not_forge_audio(self):
        def unavailable(route, episode, environment):
            raise v.ProviderUnavailable("offline")
        with self.assertRaisesRegex(RuntimeError,
                                   "ALL_APPROVED_TTS_PROVIDERS_UNAVAILABLE:cloud,local_pc,chatterbox_v3"):
            v.synthesize(EPISODE,env=env(),transport=unavailable)
        bad=env()
        for k in ("GUSTAVA_SELFHOSTED_TTS_ENABLED","GUSTAVA_LOCAL_TTS_ENABLED",
                  "GUSTAVA_TERTIARY_TTS_ENABLED"):
            bad[k]="0"
        with self.assertRaisesRegex(RuntimeError,"NO_CONFIGURED_APPROVED_TTS_PROVIDER"):
            v.synthesize(EPISODE,env=bad,transport=unavailable)

if __name__=="__main__":
    unittest.main()
