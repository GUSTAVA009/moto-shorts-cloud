"""Offline tests: own API secrets, no external quotas, durable idempotency."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Ledger, Denied, VOICE_ID, check_wav, sha


def wav(seconds=2.5, rate=24000):
    import array
    frames = array.array("h", [3000, -3000] * (int(seconds*rate)//2))
    out=io.BytesIO()
    with wave.open(out,"wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate)
        f.writeframes(frames.tobytes())
    return out.getvalue()


class OwnServerLedgerTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store=Ledger(Path(self.folder.name))
        self.issued=self.store.create_key("YouTube Factory",0,5)
        self.account=self.store.authenticate(self.issued["api_key"])

    def test_secret_is_random_256bits_shown_once_hashed_in_database(self):
        first=self.issued["api_key"]
        second=self.store.create_key("Separate user")["api_key"]
        self.assertTrue(first.startswith("gvk_"))
        self.assertGreaterEqual(len(first),45)
        self.assertNotEqual(first,second)
        raw=self.store.path.read_bytes()
        self.assertNotIn(first.encode(),raw)
        self.assertNotIn(second.encode(),raw)
        with self.store.connection() as db:
            stored=db.execute("SELECT token_hash FROM keys WHERE id=?",
                              (self.issued["id"],)).fetchone()[0]
        self.assertEqual(stored,hashlib.sha256(first.encode()).hexdigest())
        listed=self.store.list_keys()
        self.assertNotIn("token_hash",str(listed))
        self.assertNotIn("api_key",str(listed))
        self.store.revoke(self.issued["id"])
        with self.assertRaisesRegex(Denied,"API_KEY_INVALID"):
            self.store.authenticate(first)
        with self.assertRaisesRegex(Denied,"API_KEY_NOT_ACTIVE"):
            self.store.revoke(self.issued["id"])

    def test_default_owner_unlimited_monthly_not_provider_paid(self):
        self.assertEqual(self.issued["max_chars_month"],0)
        self.assertEqual(self.store.list_keys()[0]["max_chars_month"],0)
        self.assertEqual(VOICE_ID,"gustava-original-v1")
        with self.assertRaises(ValueError):
            self.store.create_key("Bad", -1)
        with self.assertRaises(ValueError):
            self.store.create_key("Bad",0,0)
        self.assertNotIn("Cartesia",str(self.store.list_keys()))

    def test_idempotency_returns_exact_saved_wav_without_second_generation(self):
        fid=sha(b"same-script")
        t=1730419200
        a=self.store.reserve(self.account,"moto-episode-01",fid,140,t)
        self.assertEqual(a,{"cached":False})
        with self.assertRaisesRegex(Denied,"NEVER_RETRY_BLINDLY"):
            self.store.reserve(self.account,"moto-episode-01",fid,140,t)
        receipt=self.store.finish(self.account["id"],"moto-episode-01",wav())
        cached=self.store.reserve(self.account,"moto-episode-01",fid,140,t)
        self.assertTrue(cached["cached"])
        self.assertEqual(self.store.get_cached(cached),wav())
        self.assertEqual(cached["sha256"],receipt["sha256"])
        with self.assertRaisesRegex(Denied,"DIFFERENT_TEXT"):
            self.store.reserve(self.account,"moto-episode-01",sha(b"different"),140,t)
        with self.store.connection() as db:
            counted=db.execute("SELECT chars FROM usage").fetchone()["chars"]
            self.assertEqual(counted,140)

    def test_bounded_owner_quota_and_rpm_are_separate_from_provider_limits(self):
        issued=self.store.create_key("Limited agent",max_chars_month=120,max_rpm=2)
        key=self.store.authenticate(issued["api_key"])
        now=1761976800
        self.store.reserve(key,"test-request-01",sha(b"one"),60,now)
        self.store.reserve(key,"test-request-02",sha(b"two"),60,now)
        with self.assertRaisesRegex(Denied,"OWN_SERVER_RATE_LIMIT"):
            self.store.reserve(key,"test-request-03",sha(b"three"),1,now)
        with self.assertRaisesRegex(Denied,"KEY_OWNER_SET_MONTHLY_LIMIT"):
            self.store.reserve(key,"test-request-04",sha(b"four"),1,now+61)
        other=self.store.create_key("Other key")
        self.assertEqual(self.store.reserve(
            self.store.authenticate(other["api_key"]),
            "test-request-05",sha(b"five"),99,now),{"cached":False})

    def test_concurrent_jobs_cannot_bill_or_generate_same_audio_twice(self):
        fid=sha(b"concurrent-text")
        def attempt(_):
            try:return self.store.reserve(self.account,"same-idem-forever",fid,37,1761976800)
            except Denied as error: return str(error)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(attempt,range(8)))
        self.assertEqual(sum(isinstance(x,dict) for x in results),1)
        self.assertEqual(sum("NEVER_RETRY_BLINDLY" in x for x in results
                             if isinstance(x,str)),7)
        with self.store.connection() as db:
            counted=db.execute("SELECT chars FROM usage").fetchone()["chars"]
        self.assertEqual(counted,37)

    def test_cached_sha_tamper_and_path_escape_blocked(self):
        ident="unique-moto-short-001";fid=sha(b"some script")
        self.store.reserve(self.account,ident,fid,31,1761976800)
        receipt=self.store.finish(self.account["id"],ident,wav())
        path=Path(receipt["file_path"])
        path.write_bytes(b"nasty audio")
        with self.assertRaises(Denied):
            self.store.get_cached(self.store.reserve(
                self.account,ident,fid,31,1761976800))
        with self.assertRaisesRegex(Denied,"CACHED_VOICE_FILE_MISSING"):
            self.store.get_cached({"file_path":"/etc/passwd","sha256":"abc"})

    def test_invalid_wav_denied_before_appearing_as_finished_audio(self):
        rate,seconds=check_wav(wav())
        self.assertEqual(rate,24000)
        self.assertAlmostEqual(seconds,2.5)
        for data in (b"not an audio", b"RIFF......",wav(.5),
                     wav(90),wav()[:500]):
            with self.subTest(length=len(data)):
                with self.assertRaises(ValueError):
                    check_wav(data)

    def test_invalid_api_key_and_idempotency_rejected_without_any_quota(self):
        for secret in ("", "hello", "gvk_short", self.issued["api_key"][:-1]+"?"):
            with self.assertRaises(Denied):
                self.store.authenticate(secret)
        with self.assertRaisesRegex(Denied,"IDEMPOTENCY_KEY_REQUIRED"):
            self.store.reserve(self.account,"../danger",sha(b"script"),100)
        with self.assertRaisesRegex(Denied,"TEXT_LENGTH"):
            self.store.reserve(self.account,"valid-idem-01",sha(b"script"),601)
        with self.store.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM usage").fetchone()[0],0)


if __name__ == "__main__":
    unittest.main()
