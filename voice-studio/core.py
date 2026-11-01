"""GUSTAVA Voice Studio: local, quota-optional credential and request ledger.

The model is SELF-HOSTED. Keys are generated with 256 bits of randomness;
the database stores only SHA-256 hashes. There is no Cartesia dependency,
external TTS quota, remote telemetry, or authorization bypass.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import array
import hashlib
import hmac
import io
from pathlib import Path
import re
import secrets
import sqlite3
import time
import wave

VOICE_ID = "gustava-original-v1"
PRIMARY_CHANNEL = "gustava"
PRIMARY_YOUTUBE_CHANNEL_ID = "UCS0QCodPcFBTjMt4ioEWOUw"
CHANNEL_RE = re.compile(r"[a-z][a-z0-9-]{2,39}\Z")
YOUTUBE_RE = re.compile(r"UC[A-Za-z0-9_-]{22}\Z")


def voice_id_for(slug: str) -> str:
    if not isinstance(slug,str) or not CHANNEL_RE.fullmatch(slug):
        raise ValueError("INVALID_YOUTUBE_CHANNEL_SLUG")
    return VOICE_ID if slug == PRIMARY_CHANNEL else "hapych-" + slug + "-original-v1"

MAX_INPUT_CHARS = 600
MAX_AUDIO_BYTES = 12_000_000
IDEMP_RE = re.compile(r"[A-Za-z0-9_.:-]{8,96}\Z")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_wav(data: bytes) -> tuple[int, float]:
    if not isinstance(data, bytes) or len(data) > MAX_AUDIO_BYTES:
        raise ValueError("AUDIO_TOO_LARGE_OR_NOT_BYTES")
    try:
        with wave.open(io.BytesIO(data), "rb") as f:
            channels, width, rate = (f.getnchannels(), f.getsampwidth(),
                                     f.getframerate())
            frames = f.getnframes()
            duration = frames / rate if rate else 0
            pcm = f.readframes(frames)
    except (ValueError, EOFError, wave.Error, ZeroDivisionError) as exc:
        raise ValueError("AUDIO_NOT_A_VALID_WAV") from exc
    if channels != 1 or width != 2 or not 12000 <= rate <= 48000:
        raise ValueError("AUDIO_REQUIRES_PCM16_MONO")
    if not 1.5 <= duration <= 65:
        raise ValueError("AUDIO_DURATION_UNSAFE")
    # WAV header or silent audio is not a produced voice. Sample the
    # audio amplitude; independent Russian ASR remains the stronger gate.
    if len(data) < frames * channels * width + 40 or len(pcm) != frames * width:
        raise ValueError("AUDIO_TRUNCATED")
    samples = array.array("h")
    samples.frombytes(pcm)
    if not samples or max(abs(n) for n in samples[::100]) < 150:
        raise ValueError("AUDIO_SILENT")
    return rate, round(duration, 3)


class Denied(RuntimeError):
    def __init__(self, reason: str, status: int = 403):
        super().__init__(reason)
        self.status = status


class Ledger:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "audio").mkdir(exist_ok=True)
        self.path = self.root / "voice-keys.sqlite3"
        with self.connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS channels (
                slug TEXT PRIMARY KEY, name TEXT NOT NULL,
                youtube_channel_id TEXT UNIQUE,
                created_at INTEGER NOT NULL,
                voice_timbre TEXT NOT NULL,
                voice_delivery TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
                max_chars_month INTEGER NOT NULL DEFAULT 0,
                max_rpm INTEGER NOT NULL DEFAULT 12,
                channel_slug TEXT REFERENCES channels(slug)
            );
            CREATE TABLE IF NOT EXISTS usage (
                key_id INTEGER NOT NULL, month TEXT NOT NULL,
                chars INTEGER NOT NULL,
                PRIMARY KEY (key_id, month)
            );
            CREATE TABLE IF NOT EXISTS requests (
                key_id INTEGER NOT NULL, idempotency TEXT NOT NULL,
                payload_hash TEXT NOT NULL, characters INTEGER NOT NULL,
                created_at INTEGER NOT NULL, status TEXT NOT NULL,
                sha256 TEXT, file_path TEXT,
                PRIMARY KEY (key_id, idempotency)
            );
            CREATE INDEX IF NOT EXISTS requests_recent
                ON requests (key_id, created_at);
            """)
            # Upgrade older installed SQLite databases without losing hashes
            # or charging an old unscoped key against the wrong YouTube channel.
            names={r["name"] for r in db.execute("PRAGMA table_info(keys)")}
            if "channel_slug" not in names:
                db.execute("ALTER TABLE keys ADD COLUMN channel_slug TEXT")
            db.execute(
                "INSERT OR IGNORE INTO channels"
                "(slug,name,youtube_channel_id,created_at,voice_timbre,voice_delivery)"
                " VALUES(?,?,?,?,?,?)",
                (PRIMARY_CHANNEL,"GUSTAVA Enduro",PRIMARY_YOUTUBE_CHANNEL_ID,
                 int(time.time()),"deep","documentary"))
            db.execute("CREATE INDEX IF NOT EXISTS keys_by_channel"
                       " ON keys(channel_slug)")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA busy_timeout=30000")
            db.execute("PRAGMA journal_mode=WAL")
            yield db
        finally:
            if db.in_transaction:
                db.rollback()
            db.close()

    def create_channel(self, slug: str, name: str,
                       timbre: str = "deep", delivery: str = "documentary",
                       youtube_channel_id: str | None = None):
        voice_id = voice_id_for(slug)
        if not isinstance(name,str) or not 2 <= len(name) <= 72:
            raise ValueError("CHANNEL_DISPLAY_NAME_INVALID")
        if timbre not in ("deep","velvet","resonant"):
            raise ValueError("CHANNEL_TIMBRE_INVALID")
        if delivery not in ("documentary","dynamic","ironic"):
            raise ValueError("CHANNEL_DELIVERY_INVALID")
        if (youtube_channel_id is not None
                and (not isinstance(youtube_channel_id,str)
                     or not YOUTUBE_RE.fullmatch(youtube_channel_id))):
            raise ValueError("YOUTUBE_CHANNEL_ID_INVALID")
        with self.connection() as db:
            try:
                db.execute(
                    "INSERT INTO channels"
                    "(slug,name,youtube_channel_id,created_at,"
                    "voice_timbre,voice_delivery)"
                    "VALUES(?,?,?,?,?,?)",
                    (slug,name,youtube_channel_id,int(time.time()),
                     timbre,delivery))
            except sqlite3.IntegrityError:
                raise Denied("CHANNEL_ALREADY_EXISTS_OR_DUPLICATE_YOUTUBE_ID",409) from None
        return {
            "slug":slug,"name":name,"voice_id":voice_id,
            "youtube_channel_id":youtube_channel_id,
            "timbre":timbre,"delivery":delivery,
        }

    def get_channel(self,slug: str):
        voice_id=voice_id_for(slug)
        with self.connection() as db:
            row=db.execute(
                "SELECT slug,name,youtube_channel_id,created_at,"
                "voice_timbre,voice_delivery FROM channels WHERE slug=?",
                (slug,)).fetchone()
        if row is None:
            raise Denied("UNKNOWN_YOUTUBE_CHANNEL",404)
        return dict(row)|{"voice_id":voice_id}

    def list_channels(self):
        with self.connection() as db:
            return [
                dict(row)|{"voice_id":voice_id_for(row["slug"])}
                for row in db.execute(
                  "SELECT c.slug,c.name,c.youtube_channel_id,"
                  "c.voice_timbre,c.voice_delivery,c.created_at,"
                  "(SELECT COUNT(*) FROM keys k WHERE k.channel_slug=c.slug "
                  "AND k.revoked=0) AS active_keys"
                  " FROM channels c ORDER BY c.created_at,c.slug")
            ]

    def create_key(self, label: str, max_chars_month: int = 0,
                   max_rpm: int = 12, channel_slug: str = PRIMARY_CHANNEL):
        if not isinstance(label, str) or not re.fullmatch(r"[\w .-]{2,72}", label):
            raise ValueError("KEY_LABEL_INVALID")
        if (type(max_chars_month) is not int or
                not 0 <= max_chars_month <= 100_000_000):
            raise ValueError("KEY_QUOTA_INVALID")
        if type(max_rpm) is not int or not 1 <= max_rpm <= 120:
            raise ValueError("KEY_RATE_LIMIT_INVALID")
        self.get_channel(channel_slug)
        token = "gvk_" + secrets.token_urlsafe(32)
        with self.connection() as db:
            cur = db.execute(
                "INSERT INTO keys(label,token_hash,created_at,"
                "max_chars_month,max_rpm,channel_slug)"
                " VALUES(?,?,?,?,?,?)",
                (label,sha(token.encode()),int(time.time()),
                 max_chars_month,max_rpm,channel_slug))
            key_id = cur.lastrowid
        return {"id": key_id, "label": label, "api_key": token,
                "channel_slug":channel_slug,
                "voice_id":voice_id_for(channel_slug),
                "max_chars_month": max_chars_month, "max_rpm": max_rpm,
                "warning": "API key shown once; save securely"}

    def list_keys(self,channel_slug=None):
        with self.connection() as db:
            if channel_slug is None:
                cursor=db.execute(
                    "SELECT id,label,created_at,revoked,max_chars_month,max_rpm,"
                    "channel_slug FROM keys ORDER BY id DESC")
            else:
                self.get_channel(channel_slug)
                cursor=db.execute(
                    "SELECT id,label,created_at,revoked,max_chars_month,max_rpm,"
                    "channel_slug FROM keys WHERE channel_slug=? ORDER BY id DESC",
                    (channel_slug,))
            return [dict(row) for row in cursor]
        
    def revoke(self, key_id: int):
        with self.connection() as db:
            result = db.execute(
                "UPDATE keys SET revoked=1 WHERE id=? AND revoked=0", (key_id,))
            if result.rowcount != 1:
                raise Denied("API_KEY_NOT_ACTIVE", 404)

    def authenticate(self, token: str):
        if (not isinstance(token, str) or
                not re.fullmatch(r"gvk_[A-Za-z0-9_-]{40,64}", token)):
            raise Denied("API_KEY_INVALID", 401)
        with self.connection() as db:
            row = db.execute(
                "SELECT id, token_hash, revoked, max_chars_month, max_rpm,"
                " channel_slug FROM keys WHERE token_hash=?", (sha(token.encode()),)).fetchone()
        if (row is None or row["revoked"] or
                not hmac.compare_digest(row["token_hash"], sha(token.encode()))):
            raise Denied("API_KEY_INVALID", 401)
        if not row["channel_slug"]:
            raise Denied("LEGACY_API_KEY_REISSUE_FOR_CHANNEL_REQUIRED",401)
        return dict(row)

    def cache_location(self, key_id: int, request_id: str):
        return self.root / "audio" / (
            str(key_id) + "-" + sha(request_id.encode())[:32] + ".wav")

    def reserve(self, account: dict, request_id: str, fingerprint: str,
                length: int, now: int | None = None):
        if not isinstance(request_id, str) or not IDEMP_RE.fullmatch(request_id):
            raise Denied("IDEMPOTENCY_KEY_REQUIRED", 400)
        if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise Denied("TEXT_FINGERPRINT_INVALID", 400)
        if not 1 <= length <= MAX_INPUT_CHARS:
            raise Denied("TEXT_LENGTH_OUTSIDE_RANGE", 400)
        timestamp = int(time.time() if now is None else now)
        month = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            # Revocation must hold even if the client was authenticated earlier
            # while another admin transaction revoked this very key.
            key = db.execute(
                "SELECT revoked,max_chars_month,max_rpm,channel_slug"
                " FROM keys WHERE id=?",
                (account["id"],)).fetchone()
            if not key or key["revoked"] or not key["channel_slug"]:
                db.execute("ROLLBACK")
                raise Denied("API_KEY_REVOKED_OR_UNSCOPED",401)
            if key["channel_slug"] != account.get("channel_slug"):
                db.execute("ROLLBACK")
                raise Denied("API_KEY_CANNOT_SWITCH_YOUTUBE_CHANNEL",403)
            previous = db.execute(
                "SELECT payload_hash,status,sha256,file_path FROM requests"
                " WHERE key_id=? AND idempotency=?",
                (account["id"], request_id)).fetchone()
            if previous:
                db.execute("COMMIT")
                if previous["payload_hash"] != fingerprint:
                    raise Denied("IDEMPOTENCY_REUSED_WITH_DIFFERENT_TEXT", 409)
                if previous["status"] == "complete":
                    return {"cached": True, "sha256": previous["sha256"],
                            "file_path": previous["file_path"]}
                # Never make an ambiguous synthesis call twice.
                raise Denied("REQUEST_ALREADY_RESERVED_NEVER_RETRY_BLINDLY", 409)
            count = db.execute(
                "SELECT COUNT(1) AS n FROM requests"
                " WHERE key_id=? AND created_at>?",
                (account["id"], timestamp - 60)).fetchone()["n"]
            if count >= key["max_rpm"]:
                db.execute("ROLLBACK")
                raise Denied("OWN_SERVER_RATE_LIMIT", 429)
            spent = db.execute(
                "SELECT chars FROM usage WHERE key_id=? AND month=?",
                (account["id"], month)).fetchone()
            amount = spent["chars"] if spent else 0
            if key["max_chars_month"] and amount + length > key["max_chars_month"]:
                db.execute("ROLLBACK")
                raise Denied("KEY_OWNER_SET_MONTHLY_LIMIT", 429)
            db.execute(
                "INSERT INTO requests(key_id,idempotency,payload_hash,characters,"
                "created_at,status) VALUES(?,?,?,?,?,?)",
                (account["id"], request_id, fingerprint, length,
                 timestamp, "reserved"))
            db.execute(
                "INSERT INTO usage(key_id,month,chars) VALUES(?,?,?)"
                " ON CONFLICT(key_id,month)"
                " DO UPDATE SET chars=chars+excluded.chars",
                (account["id"], month, length))
            db.execute("COMMIT")
        return {"cached": False}

    def finish(self, key_id: int, request_id: str, data: bytes):
        check_wav(data)
        digest = sha(data)
        dst = self.cache_location(key_id, request_id)
        temp = dst.with_suffix("." + secrets.token_hex(8) + ".tmp")
        temp.write_bytes(data)
        try:
            temp.replace(dst)
            with self.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                cur = db.execute(
                    "UPDATE requests SET status='complete',sha256=?,file_path=?"
                    " WHERE key_id=? AND idempotency=? AND status='reserved'",
                    (digest, str(dst), key_id, request_id))
                if cur.rowcount != 1:
                    db.execute("ROLLBACK")
                    raise Denied("REQUEST_RESERVATION_CHANGED", 409)
                db.execute("COMMIT")
            return {"sha256": digest, "file_path": str(dst)}
        finally:
            temp.unlink(missing_ok=True)

    def get_cached(self, record: dict):
        path = Path(record["file_path"])
        if not path.is_file() or path.parent.resolve() != (
                self.root / "audio").resolve():
            raise Denied("CACHED_VOICE_FILE_MISSING", 503)
        data = path.read_bytes()
        try:
            check_wav(data)
        except ValueError:
            raise Denied("CACHED_VOICE_INVALID_WAV", 503) from None
        if sha(data) != record["sha256"]:
            raise Denied("CACHED_VOICE_SHA_MISMATCH", 503)
        return data
