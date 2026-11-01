#!/usr/bin/env python3
"""Official Cartesia Sonic 3.6 API: single-voice, Russian, SHA-pinned TTS.

Only PRIVATE previews may consume API credits. Old original AIDocMaker DEEP
recordings remain untouched. A verified, native Russian masculine voice UUID
must be selected and pinned per episode. Never log or commit the API key.

The first paid/uncertain request reserves its full text length durably BEFORE
contacting Cartesia. This may conservatively count a request that did not bill.
No retry after an uncertain request and no overages without explicit approval.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request
import uuid
import wave

from deep_voice import pcm_stats, provenance_path

VOICE_ENGINE = "cartesia_sonic36"
PROFILE_ID = "gustava_cartesia_ru_male_v1"
MODEL_ID = "sonic-3.6-2026-08-27"  # immutable official stable snapshot
API_VERSION = "2026-08-14"
BASE = "https://api.cartesia.ai"
MAX_SOURCE_BYTES = 6_000_000
MAX_RECORDS = 600
DEFAULT_MONTHLY_CHAR_CAP = 15_000
LEGACY_ENGINE = "aidocmaker_deep"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def parse_voice_id(value):
    if not isinstance(value, str):
        raise ValueError("CARTESIA_VOICE_ID_NOT_SET")
    try:
        normal = str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("CARTESIA_VOICE_ID_INVALID") from exc
    if value != normal:
        raise ValueError("CARTESIA_VOICE_ID_NOT_CANONICAL")
    return value


def supported_episode(episode):
    if episode.get("voice_engine") != VOICE_ENGINE:
        return False
    if episode.get("voice_profile") != PROFILE_ID:
        return False
    try:
        parse_voice_id(episode.get("cartesia_voice_id"))
    except ValueError:
        return False
    return True


def ready(episode, environment=None):
    """A preflight hint, not verified audio or permission to auto-publish."""
    env = environment if environment is not None else os.environ
    return bool(supported_episode(episode)
                and env.get("CARTESIA_TTS_ENABLED") == "1"
                and (env.get("CARTESIA_KEY_PRESENT") == "true"
                     or bool(env.get("CARTESIA_API_KEY")))
                and episode.get("auto_publish") is not True)


def verify_voice_metadata(obj, expected_id):
    """Reject female, unverified and non-native-Russian library voices."""
    if (not isinstance(obj, dict) or obj.get("id") != expected_id
            or obj.get("status") != "active"
            or obj.get("gender") != "masculine"):
        raise ValueError("CARTESIA_MASCULINE_VOICE_UNVERIFIED")
    language = str(obj.get("language") or "").replace("_", "-").casefold()
    native = language == "ru" or language.startswith("ru-")
    for accent in obj.get("accents") or []:
        if (isinstance(accent, dict)
                and str(accent.get("locale") or "").casefold().startswith("ru-")
                and accent.get("is_native") is True):
            native = True
    if not native:
        raise ValueError("CARTESIA_NATIVE_RUSSIAN_VOICE_REQUIRED")
    return expected_id


def _key():
    key = os.environ.get("CARTESIA_API_KEY", "")
    if not key.startswith("sk_car_") or len(key) < 16:
        raise RuntimeError("CARTESIA_GITHUB_ACTIONS_SECRET_NOT_INSTALLED")
    return key


def request(path, *, payload=None, max_bytes=MAX_SOURCE_BYTES, opener=None):
    """No key in request URL, errors, logging, stored files or exception text."""
    if not path.startswith("/") or "?" in path or ".." in path:
        raise ValueError("CARTESIA_API_PATH_NOT_ALLOWED")
    if not (path == "/tts/bytes" or
            re.fullmatch(r"/voices/[0-9a-f-]{36}", path)):
        raise ValueError("CARTESIA_API_UNAPPROVED_ROUTE")
    headers = {
        "Authorization": "Bearer " + _key(),
        "Cartesia-Version": API_VERSION,
        "Accept": "audio/wav" if payload is not None else "application/json",
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf8") if payload is not None else None
    if raw is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        BASE + path, headers=headers, data=raw,
        method="POST" if raw is not None else "GET"
    )
    try:
        operation = opener or urllib.request.urlopen
        with operation(req, timeout=60) as response:
            if response.geturl() != BASE + path:
                raise RuntimeError("CARTESIA_CROSS_HOST_REDIRECT_REFUSED")
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise RuntimeError("CARTESIA_AUDIO_OR_METADATA_TOO_LARGE")
            return body
    except urllib.error.HTTPError as error:
        # Never include response body, headers, source URL or token.
        raise RuntimeError("CARTESIA_HTTP_" + str(error.code)) from None
    except urllib.error.URLError:
        raise RuntimeError("CARTESIA_NETWORK_UNAVAILABLE") from None


def _github_api(method, path, data=None):
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if (not token or os.environ.get("GITHUB_REPOSITORY") !=
            "GUSTAVA009/moto-shorts-cloud"):
        raise RuntimeError("CARTESIA_NO_AUTHORIZED_GITHUB_LEDGER")
    url = ("https://api.github.com/repos/GUSTAVA009/moto-shorts-cloud/" + path)
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "gustava-cartesia-budget-ledger",
    }
    wire = json.dumps(data).encode("utf8") if data is not None else None
    if wire is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, headers=headers, data=wire, method=method)
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as error:
        if method == "GET" and error.code == 404:
            return None
        # A concurrent commit is not permission to retry a paid call.
        raise RuntimeError("CARTESIA_LEDGER_HTTP_" + str(error.code)) from None


def monthly_limit(env=None):
    env = env if env is not None else os.environ
    try:
        limit = int(env.get("CARTESIA_MONTHLY_CHAR_LIMIT",
                            str(DEFAULT_MONTHLY_CHAR_CAP)))
    except (TypeError, ValueError) as error:
        raise ValueError("CARTESIA_MONTHLY_LIMIT_INVALID") from error
    if not 1 <= limit <= 20_000:
        if not (20_000 < limit <= 250_000
                and env.get("CARTESIA_COMMERCIAL_PLAN_CONFIRMED") == "1"):
            raise ValueError("CARTESIA_MONTHLY_LIMIT_NEEDS_COMMERCIAL_APPROVAL")
    return limit


def reserve_spend(episode, ledger_api=_github_api, now=None, env=None):
    """Budget-before-call; never refund or replay an unknown charge."""
    if not supported_episode(episode):
        raise ValueError("CARTESIA_EPISODE_PROFILE_NOT_PINNED")
    env = env if env is not None else os.environ
    if env.get("CARTESIA_TTS_ENABLED") != "1":
        raise RuntimeError("CARTESIA_TTS_NOT_ENABLED")
    if episode.get("auto_publish") is True:
        raise RuntimeError("CARTESIA_NEW_VOICE_MUST_BE_PRIVATE_FIRST")
    date = (now or datetime.now(timezone.utc)).strftime("%Y-%m")
    path = "contents/voice-usage/cartesia-" + date + ".json"
    existing = ledger_api("GET", path + "?ref=render-ledger")
    if existing is None:
        ledger = {"version": 1, "month": date, "records": {}}
    else:
        try:
            ledger = json.loads(base64.b64decode(existing["content"]))
        except (ValueError, TypeError, KeyError) as error:
            raise RuntimeError("CARTESIA_BUDGET_LEDGER_INVALID") from error
    if (not isinstance(ledger, dict)
            or ledger.get("version") != 1 or ledger.get("month") != date
            or not isinstance(ledger.get("records"), dict)
            or len(ledger["records"]) > MAX_RECORDS):
        raise RuntimeError("CARTESIA_BUDGET_LEDGER_INVALID")
    records = ledger["records"]
    for record in records.values():
        if (not isinstance(record, dict)
                or type(record.get("chars")) is not int
                or not 1 <= record["chars"] <= 350):
            raise RuntimeError("CARTESIA_BUDGET_LEDGER_CORRUPT")
    if episode["id"] in records:
        raise RuntimeError("CARTESIA_ALREADY_RESERVED_NO_DUPLICATE_CALL")
    transcript = episode["narration"]
    if not isinstance(transcript, str) or not 125 <= len(transcript) <= 350:
        raise ValueError("CARTESIA_TRANSCRIPT_LENGTH_OUTSIDE_SHORTS")
    amount = len(transcript)
    consumed = sum(item["chars"] for item in records.values())
    if consumed + amount > monthly_limit(env):
        raise RuntimeError("CARTESIA_MONTHLY_CHARACTER_BUDGET_EXHAUSTED")
    records[episode["id"]] = {
        "chars": amount,
        "text_sha256": sha(transcript.encode("utf8")),
        "voice_id": episode["cartesia_voice_id"],
        "model_id": MODEL_ID,
    }
    payload = {
        "message": "Reserve Cartesia capped credits for private " + episode["id"],
        "branch": "render-ledger",
        "content": base64.b64encode(
            (json.dumps(ledger, sort_keys=True, indent=2) + "\n").encode("utf8")
        ).decode("ascii"),
    }
    if existing:
        if not existing.get("sha"):
            raise RuntimeError("CARTESIA_LEDGER_MISSING_SHA")
        payload["sha"] = existing["sha"]
    ledger_api("PUT", path, payload)
    return amount


def _wav_bytes_valid(content):
    try:
        with wave.open(io.BytesIO(content), "rb") as wave_file:
            params = (wave_file.getnchannels(), wave_file.getsampwidth(),
                      wave_file.getframerate())
            seconds = wave_file.getnframes() / wave_file.getframerate()
    except (ValueError, EOFError, wave.Error) as error:
        raise ValueError("CARTESIA_INVALID_WAV_BYTES") from error
    if (params != (1, 2, 44100) or not 3.0 <= seconds <= 35.0
            or len(content) > MAX_SOURCE_BYTES):
        raise ValueError("CARTESIA_WAV_FORMAT_OR_DURATION_UNSAFE")
    return round(seconds, 3)


def verify_profile(wav, episode):
    if not supported_episode(episode):
        raise ValueError("CARTESIA_INVALID_VOICE_PROFILE")
    file = Path(wav)
    sidecar = provenance_path(file)
    if not sidecar.is_file() or not file.is_file():
        raise ValueError("CARTESIA_PROVENANCE_MISSING")
    try:
        record = json.loads(sidecar.read_text(encoding="utf8"))
    except (OSError, ValueError) as error:
        raise ValueError("CARTESIA_PROVENANCE_INVALID") from error
    required = {
        "episode_id": episode["id"], "voice_engine": VOICE_ENGINE,
        "voice_profile": PROFILE_ID,
        "voice_id": episode["cartesia_voice_id"],
        "model_id": MODEL_ID,
        "text_sha256": sha(episode["narration"].encode("utf8")),
        "wav_sha256": sha(file.read_bytes()),
    }
    if any(record.get(k) != v for k, v in required.items()):
        raise ValueError("CARTESIA_PROVENANCE_MISMATCH")
    if not re.fullmatch(r"[0-9a-f]{64}", record.get("source_audio_sha256") or ""):
        raise ValueError("CARTESIA_SOURCE_SHA_NOT_PINNED")
    stats = pcm_stats(file)  # same lossless 24-kHz, mono, voice-level checks as DEEP
    if abs(stats["duration_seconds"] - record.get("duration_seconds", -1)) > .02:
        raise ValueError("CARTESIA_AUDIO_DURATION_MISMATCH")
    return record


def render(episode, destination, api_request=request, spend_reserver=reserve_spend):
    """One billed request, cached across local QA rerenders, never re-spent."""
    if not supported_episode(episode):
        raise RuntimeError("CARTESIA_VOICE_OR_PROFILE_UNCONFIGURED")
    target = Path(destination)
    # Reuse the exact recorded take when only music gain changes.
    if target.is_file() or provenance_path(target).is_file():
        report = verify_profile(target, episode)
        return report["duration_seconds"]
    if not os.environ.get("CARTESIA_API_KEY"):
        raise RuntimeError("CARTESIA_GITHUB_ACTIONS_SECRET_NOT_INSTALLED")
    if os.environ.get("CARTESIA_TTS_ENABLED") != "1":
        raise RuntimeError("CARTESIA_TTS_NOT_ENABLED")
    voice = episode["cartesia_voice_id"]
    info = json.loads(api_request("/voices/" + voice, max_bytes=50_000))
    verify_voice_metadata(info, voice)
    # This is intentionally BEFORE the charged API request. On uncertain
    # network/HTTP failures the reservation persists; no blind paid retries.
    spend_reserver(episode)
    payload = {
        "model_id": MODEL_ID,
        "transcript": episode["narration"],
        "voice": voice,
        "language": "ru",
        "output_format": {
            "container": "wav", "encoding": "pcm_s16le", "sample_rate": 44100
        },
        "generation_config": {"speed": 1.0, "volume": 1.0},
    }
    content = api_request("/tts/bytes", payload=payload)
    _wav_bytes_valid(content)
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = target.with_name(target.stem + ".cartesia-source.wav")
    tmp = target.with_name(target.stem + ".cartesia-tmp.wav")
    try:
        raw.write_bytes(content)
        subprocess.run([
            "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
            "-y", "-i", str(raw), "-vn", "-ac", "1", "-ar", "24000",
            "-c:a", "pcm_s16le", str(tmp)
        ], check=True, capture_output=True, timeout=90)
        stats = pcm_stats(tmp)
        tmp.replace(target)
        record = {
            "episode_id": episode["id"], "voice_engine": VOICE_ENGINE,
            "voice_profile": PROFILE_ID, "voice_id": voice,
            "model_id": MODEL_ID,
            "text_sha256": sha(episode["narration"].encode("utf8")),
            "source_audio_sha256": sha(content),
            "wav_sha256": sha(target.read_bytes()),
            "duration_seconds": stats["duration_seconds"],
            "license_status": "provider_commercial_plan_to_be_verified",
            "pitch_shift": 1.0, "voice_layers": 1,
        }
        provenance_path(target).write_text(
            json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf8")
        verify_profile(target, episode)
        print("CARTESIA_PRIVATE_AUDIO_READY", episode["id"],
              "duration", stats["duration_seconds"], flush=True)
        return stats["duration_seconds"]
    finally:
        raw.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)
