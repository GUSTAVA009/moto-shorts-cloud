"""No-network official Cartesia Sonic 3.6 provider and spending-regression tests."""
import base64
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import wave

import cartesia_voice as c

VOICE = "0f111c12-cabc-4ba0-9a29-1ef98b133e90"
TEXT = ("Говорят, что туристический мотоцикл подходит только для спокойной "
        "дороги. Посмотри на два совершенно разных маршрута. На одном "
        "байкер едет в путешествие, а на другом начинается настоящая гонка.")


def ep(n="cartesia-new-01"):
    return {
        "id": n,
        "voice_engine": c.VOICE_ENGINE,
        "voice_profile": c.PROFILE_ID,
        "cartesia_voice_id": VOICE,
        "auto_preview": True,
        "auto_publish": False,
        "narration": TEXT,
    }


def canonical_wav(rate=44100, seconds=3.3):
    import array
    samples = array.array("h", (4000 if x % 2 == 0 else -4000
                                for x in range(round(rate * seconds))))
    out = io.BytesIO()
    with wave.open(out, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(samples.tobytes())
    return out.getvalue()


class CartesiaApiTests(unittest.TestCase):
    def test_only_pinned_original_male_russian_sonic_voice_is_eligible(self):
        e = ep()
        self.assertFalse(c.ready(e, {}))
        self.assertFalse(c.ready(e, {"CARTESIA_TTS_ENABLED": "1"}))
        self.assertTrue(c.ready(
            e, {"CARTESIA_TTS_ENABLED": "1", "CARTESIA_KEY_PRESENT": "true"}))
        self.assertFalse(c.ready(
            dict(e, auto_publish=True),
            {"CARTESIA_TTS_ENABLED": "1", "CARTESIA_KEY_PRESENT": "true"}))
        self.assertFalse(c.ready(dict(e, voice_engine="aidocmaker_deep"),
                                 {"CARTESIA_TTS_ENABLED": "1",
                                  "CARTESIA_KEY_PRESENT": "true"}))
        self.assertFalse(c.supported_episode(dict(e, cartesia_voice_id="bad")))
        self.assertEqual(c.parse_voice_id(VOICE), VOICE)
        self.assertEqual(c.MODEL_ID, "sonic-3.6-2026-08-27")

    def test_native_russian_masculine_library_voice_is_required(self):
        v = {"id": VOICE, "status":"active", "gender":"masculine",
             "language":"ru","accents":[]}
        self.assertEqual(c.verify_voice_metadata(v, VOICE),VOICE)
        for bad in (
            dict(v, gender="feminine"), dict(v, status="archived"),
            dict(v, language="en"),
            dict(v, id="different"),
            dict(v, language="en", accents=[
                {"locale":"ru-RU","is_native":False}]),
        ):
            with self.assertRaises(ValueError):
                c.verify_voice_metadata(bad, VOICE)
        self.assertEqual(c.verify_voice_metadata(
            dict(v, language="en", accents=[
                {"locale":"ru-RU","is_native":True}]),VOICE),VOICE)

    def test_api_never_prints_bearer_secret_or_sends_to_external_url(self):
        observed = []
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def geturl(self): return "https://api.cartesia.ai/voices/" + VOICE
            def read(self, n): return b'{"id":"approved"}'
        def opener(req, timeout):
            observed.append((req.full_url,req.headers,
                             req.get_method(),timeout))
            return Response()
        with patch.dict("os.environ",{"CARTESIA_API_KEY":"sk_car_test-only-not-real"}):
            data=c.request("/voices/"+VOICE, max_bytes=1000, opener=opener)
        self.assertEqual(json.loads(data),{"id":"approved"})
        self.assertEqual(observed[0][2],"GET")
        self.assertEqual(observed[0][1]["Cartesia-version"],"2026-08-14")
        self.assertIn("Bearer sk_car_test-only-not-real",
                      observed[0][1]["Authorization"])
        with self.assertRaisesRegex(ValueError,"UNAPPROVED_ROUTE"):
            c.request("/evil/path", opener=opener)
        with self.assertRaisesRegex(ValueError,"PATH_NOT_ALLOWED"):
            c.request("/tts/bytes?redirect=https://attacker.example", opener=opener)

    def test_cartesia_errors_redact_all_remote_provider_messages(self):
        def unauthorized(*args, **kwargs):
            raise urllib.error.HTTPError("https://api.cartesia.ai/tts/bytes",
                                         401,"SECRET_SHOULD_NOT_LEAK",
                                         {"Authorization":"hidden"},None)
        with patch.dict("os.environ",{"CARTESIA_API_KEY":"sk_car_test-only-not-real"}):
            with self.assertRaisesRegex(RuntimeError,"CARTESIA_HTTP_401") as raised:
                c.request("/voices/"+VOICE, opener=unauthorized)
        self.assertNotIn("SECRET",str(raised.exception))
        self.assertNotIn("Bearer",str(raised.exception))

    def test_wav_audio_is_real_mono_pcm_not_mp3_or_partial_header(self):
        self.assertGreater(c._wav_bytes_valid(canonical_wav()),3)
        for malformed in (
            b"RIFFBROKENWAV",
            canonical_wav(rate=24000),
            canonical_wav(seconds=2.7),
        ):
            with self.assertRaises(ValueError):
                c._wav_bytes_valid(malformed)

    def test_budget_allocates_once_per_episode_and_blocks_repeat_charge(self):
        remote, calls = {}, []
        def github(method, path, data=None):
            calls.append(method)
            if method == "GET":
                return None if not remote else {
                    "sha":"sha-original",
                    "content":base64.b64encode(
                        json.dumps(remote).encode()).decode()}
            remote.clear()
            remote.update(json.loads(base64.b64decode(data["content"])))
            self.assertEqual(data["branch"],"render-ledger")
            return {"status":"ok"}
        with patch.dict("os.environ",{"CARTESIA_TTS_ENABLED":"1",
                                     "CARTESIA_MONTHLY_CHAR_LIMIT":"500"}):
            amount=c.reserve_spend(ep(), github,
                now=datetime(2026,11,1,tzinfo=timezone.utc))
            self.assertEqual(amount,len(TEXT))
            self.assertEqual(calls,["GET","PUT"])
            self.assertNotIn("sk_car_",json.dumps(remote))
            self.assertEqual(remote["records"][ep()["id"]]["chars"],len(TEXT))
            with self.assertRaisesRegex(RuntimeError,"ALREADY_RESERVED"):
                c.reserve_spend(ep(),github,
                    now=datetime(2026,11,1,tzinfo=timezone.utc))
            self.assertEqual(calls,["GET","PUT","GET"])
            with self.assertRaisesRegex(RuntimeError,"BUDGET_EXHAUSTED"):
                c.reserve_spend(ep("cartesia-new-02"),github,
                    now=datetime(2026,11,1,tzinfo=timezone.utc),
                    env={"CARTESIA_TTS_ENABLED":"1","CARTESIA_MONTHLY_CHAR_LIMIT":
                         str(len(TEXT)+10)})
        self.assertEqual(c.monthly_limit({}),15000)
        with self.assertRaisesRegex(ValueError,"COMMERCIAL_APPROVAL"):
            c.monthly_limit({"CARTESIA_MONTHLY_CHAR_LIMIT":"30000"})

    def test_no_tts_call_without_budget_receipt_and_voice_validation(self):
        records = []
        def api(path, **kw):
            records.append(path)
            if path.startswith("/voices/"):
                return json.dumps({"id":VOICE,"status":"active",
                                   "gender":"masculine","language":"ru"}).encode()
            return canonical_wav()
        with tempfile.TemporaryDirectory() as td, patch.dict(
            "os.environ",{"CARTESIA_API_KEY":"sk_car_test-only-not-real",
                          "CARTESIA_TTS_ENABLED":"1"}):
            # An explicit failed budget gate must never send the paid POST.
            def fail_reserve(episode):
                raise RuntimeError("BUDGET_EXHAUSTED")
            with self.assertRaisesRegex(RuntimeError,"BUDGET_EXHAUSTED"):
                c.render(ep(),Path(td)/"narration.wav",
                         api_request=api,spend_reserver=fail_reserve)
            self.assertEqual(records,["/voices/"+VOICE])
            self.assertFalse((Path(td)/"narration.wav").is_file())

    def test_provenance_rejects_source_tampering_after_render(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"voice.wav"
            p.write_bytes(canonical_wav(rate=24000,seconds=3.3))
            record={
                "episode_id":ep()["id"],"voice_engine":c.VOICE_ENGINE,
                "voice_profile":c.PROFILE_ID,"voice_id":VOICE,
                "model_id":c.MODEL_ID,"text_sha256":c.sha(TEXT.encode()),
                "source_audio_sha256":"a"*64,"wav_sha256":c.sha(p.read_bytes()),
                "duration_seconds":3.3
            }
            c.provenance_path(p).write_text(json.dumps(record))
            self.assertEqual(c.verify_profile(p,ep())["voice_id"],VOICE)
            p.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError,"PROVENANCE_MISMATCH"):
                c.verify_profile(p,ep())


if __name__ == "__main__":
    unittest.main()
