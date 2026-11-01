#!/usr/bin/env python3
"""Self-hosted branded Russian TTS API. Never calls Cartesia.

VoiceDesign creates ONE ORIGINAL fictional Russian male character. The
resulting original WAV becomes a durable reference for Base-model cloning,
so later Shorts keep an auditable voice fingerprint. Only Qwen local server
runs inference; the hosted Cartesia Sergei sample MUST NOT be used.
"""
from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import FileResponse, HTMLResponse
import httpx
from pydantic import BaseModel, ConfigDict, Field

from core import (Ledger, VOICE_ID, MAX_INPUT_CHARS, Denied,
                  check_wav, sha)

DATA = Path(os.environ.get("VOICE_STUDIO_DATA", "/data")).resolve()
ROOT = Path(__file__).resolve().parent
DATA.mkdir(parents=True, exist_ok=True)
LEDGER = Ledger(DATA)
VOICE_FILE = DATA / "voice-reference-original.wav"
VOICE_PROOF = DATA / "voice-reference-original.json"
UPSTREAM = os.environ.get("QWEN_BACKEND_URL", "http://qwen:8000").rstrip("/")
UPSTREAM_KEY = os.environ.get("UPSTREAM_API_KEY", "")
REFERENCE_TEXT = (
    "Сегодня поговорим о мотоциклах. Иногда самый короткий путь "
    "оказывается самым интересным приключением. Слушай внимательно."
)
ORIGINAL_INSTRUCTION = (
    "Create a completely ORIGINAL fictional narrator voice. Native Russian "
    "language male, mature warm low baritone, velvety and slightly textured, "
    "clear consonants and natural Russian vowels. Charismatic documentary "
    "storyteller with energetic emphasis, confident pacing and subtle irony. "
    "Natural intonation, no artificial pitch processing. Do NOT imitate any "
    "existing performer, celebrity, commercial stock voice or Cartesia voice."
)
app = FastAPI(
    title="GUSTAVA Voice Studio",
    version="0.1.0",
    description="Own-server TTS API for consented, original Russian voices",
    docs_url="/docs", redoc_url=None,
)
GPU_LOCK = asyncio.Lock()


def safe_upstream():
    from urllib.parse import urlsplit
    value = urlsplit(UPSTREAM)
    # Protect original/reference audio from accidental external disclosure.
    if (value.scheme != "http" or value.hostname not in
            {"qwen", "localhost", "127.0.0.1"}
            or value.username or value.password or value.query
            or value.fragment or value.path):
        raise RuntimeError("QWEN_BACKEND_MUST_BE_PRIVATE_CONTAINER")
    if not UPSTREAM_KEY or len(UPSTREAM_KEY) < 24:
        raise RuntimeError("QWEN_UPSTREAM_SECRET_NOT_SET")


def admin(x_admin_token: str | None = Header(default=None)):
    expected = os.environ.get("VOICE_STUDIO_ADMIN_TOKEN", "")
    if len(expected) < 32:
        raise HTTPException(503, "VOICE_ADMIN_SECRET_NOT_CONFIGURED")
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(401, "ADMIN_AUTH_REQUIRED")
    return True


class CreateKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=2, max_length=72)
    # 0 = UNLIMITED owner-side monthly characters; there is no provider quota.
    max_chars_month: int = Field(default=0, ge=0, le=100_000_000)
    max_rpm: int = Field(default=12, ge=1, le=120)


class OriginalDesign(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_original: bool
    # Use server-owned description, not a copied commercial voice reference.


class SpeechBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)
    voice: str = VOICE_ID
    response_format: str = "wav"


def exception_for(error: Denied):
    return HTTPException(error.status, str(error))


def validated_reference():
    if not VOICE_FILE.is_file() or not VOICE_PROOF.is_file():
        raise HTTPException(503, "ORIGINAL_VOICE_NOT_CREATED")
    try:
        meta = json.loads(VOICE_PROOF.read_text(encoding="utf8"))
        raw = VOICE_FILE.read_bytes()
        check_wav(raw)
        valid = (
            meta.get("source") == "selfhosted_qwen_voice_design"
            and meta.get("voice_id") == VOICE_ID
            and meta.get("wav_sha256") == sha(raw)
            and meta.get("reference_text") == REFERENCE_TEXT
            and meta.get("instruction_sha256") ==
                sha(ORIGINAL_INSTRUCTION.encode("utf8"))
        )
        if not valid:
            raise ValueError("reference proof mismatch")
        return raw, meta
    except (ValueError, OSError, KeyError, json.JSONDecodeError):
        raise HTTPException(503, "ORIGINAL_VOICE_REFERENCE_VERIFICATION_FAILED")


async def qwen_audio(route: str, payload: dict):
    safe_upstream()
    if route not in {"/api/v1/voice-design/generate",
                     "/api/v1/base/clone"}:
        raise RuntimeError("QWEN_UNAPPROVED_ROUTE")
    # No automatic retry: no parallel model inference and no duplicated
    # ambiguous synthesis. GPU model is private and subject to one-at-a-time.
    headers = {
        "X-API-Key": UPSTREAM_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/wav",
    }
    timeout = httpx.Timeout(connect=12, read=480, write=25, pool=15)
    async with GPU_LOCK:
        try:
            async with httpx.AsyncClient(timeout=timeout,
                                          follow_redirects=False,
                                          trust_env=False) as client:
                reply = await client.post(UPSTREAM + route,
                                          json=payload, headers=headers)
        except (httpx.TimeoutException, httpx.RequestError):
            raise HTTPException(502, "PRIVATE_VOICE_ENGINE_UNAVAILABLE")
    if reply.status_code != 200:
        # Upstream errors may contain request text or private key. Do not
        # forward the response body, URL, or headers to API clients.
        raise HTTPException(502, "PRIVATE_VOICE_ENGINE_GENERATION_FAILED")
    data = reply.content
    try:
        check_wav(data)
    except ValueError:
        raise HTTPException(502, "PRIVATE_VOICE_ENGINE_INVALID_WAV")
    return data


@app.middleware("http")
async def secure_site_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; media-src 'self' blob:; "
        "connect-src 'self'; object-src 'none'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    if request.url.path.startswith(("/v1/", "/api/admin/")):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/", response_class=HTMLResponse)
def home():
    return (ROOT / "index.html").read_text(encoding="utf8")


@app.get("/site.css")
def stylesheet():
    return FileResponse(ROOT / "site.css", media_type="text/css")


@app.get("/site.js")
def javascript():
    return FileResponse(ROOT / "site.js", media_type="application/javascript")


@app.get("/health")
def health():
    # This does not claim a loaded GPU model or generated voice.
    return {
        "status": "running",
        "engine": "qwen3-tts-selfhosted",
        "voice_id": VOICE_ID,
        "reference_available": VOICE_FILE.is_file() and VOICE_PROOF.is_file(),
        "audio_generated": False,
        "cartesia": False,
    }


@app.get("/api/admin/keys", dependencies=[Depends(admin)])
def keys():
    return {"keys": LEDGER.list_keys()}


@app.post("/api/admin/keys", dependencies=[Depends(admin)], status_code=201)
def create_key(body: CreateKey):
    try:
        return LEDGER.create_key(body.label, body.max_chars_month, body.max_rpm)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/admin/keys/{key_id}", dependencies=[Depends(admin)])
def revoke_key(key_id: int):
    try:
        LEDGER.revoke(key_id)
    except Denied as exc:
        raise exception_for(exc)
    return {"revoked": True, "id": key_id}


@app.get("/api/admin/voice", dependencies=[Depends(admin)])
def voice_details():
    if not VOICE_FILE.is_file() or not VOICE_PROOF.is_file():
        return {"created": False, "voice_id": VOICE_ID}
    _, meta = validated_reference()
    return {
        "created": True, "voice_id": VOICE_ID,
        "created_at": meta.get("created_at"),
        "reference_sha256": meta["wav_sha256"],
        "source": meta["source"],
    }


@app.get("/api/admin/voice/reference", dependencies=[Depends(admin)])
def original_reference():
    raw, meta = validated_reference()
    return Response(content=raw, media_type="audio/wav",
                    headers={"Cache-Control": "no-store",
                             "X-Voice-SHA256": meta["wav_sha256"]})


@app.post("/api/admin/voice/design", dependencies=[Depends(admin)])
async def create_original(body: OriginalDesign):
    if body.confirm_original is not True:
        raise HTTPException(400, "CONFIRM_ORIGINAL_NON_IMPERSONATING_VOICE")
    if VOICE_FILE.exists() or VOICE_PROOF.exists():
        raise HTTPException(409, "ORIGINAL_VOICE_IS_PINNED_DO_NOT_OVERWRITE")
    generated = await qwen_audio(
        "/api/v1/voice-design/generate",
        {"text": REFERENCE_TEXT, "language": "Russian",
         "instruct": ORIGINAL_INSTRUCTION, "response_format": "wav"},
    )
    # No product/company voice sample was used: only an original description.
    proof = {
        "source": "selfhosted_qwen_voice_design",
        "voice_id": VOICE_ID,
        "reference_text": REFERENCE_TEXT,
        "instruction_sha256": sha(ORIGINAL_INSTRUCTION.encode("utf8")),
        "wav_sha256": sha(generated),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_expected": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
        "used_cartesia_sample": False,
    }
    # Atomic create; retain first successfully designed voice. If one
    # exists, never overwrite the reference backing a production channel.
    try:
        with VOICE_FILE.open("xb") as f:
            f.write(generated)
        with VOICE_PROOF.open("x", encoding="utf8") as f:
            json.dump(proof, f, ensure_ascii=False, indent=2)
    except FileExistsError:
        raise HTTPException(409, "ORIGINAL_VOICE_IS_PINNED_DO_NOT_OVERWRITE")
    return {"voice_id": VOICE_ID, "created": True,
            "reference_sha256": proof["wav_sha256"],
            "next": "Generate a private sample before using for YouTube"}


@app.post("/v1/audio/speech")
async def speech(
    body: SpeechBody,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    x_idempotency_key: str | None = Header(default=None),
):
    token = x_api_key or (
        authorization.split(" ", 1)[1]
        if authorization and authorization.startswith("Bearer ") else None)
    try:
        account = LEDGER.authenticate(token or "")
    except Denied as exc:
        raise exception_for(exc)
    if body.voice != VOICE_ID:
        raise HTTPException(400, "ONLY_PINNED_ORIGINAL_VOICE_AVAILABLE")
    if body.response_format != "wav":
        raise HTTPException(400, "ONLY_WAV_SUPPORTED_FOR_VERIFIED_RAW_AUDIO")
    if not body.text.strip():
        raise HTTPException(400, "EMPTY_TRANSCRIPT")
    # Validate provenance before reserving GPU resources/usage.
    reference, proof = validated_reference()
    signature = sha(json.dumps(
        {"text": body.text, "voice": VOICE_ID, "response_format": "wav"},
        ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf8"))
    try:
        reservation = LEDGER.reserve(
            account, x_idempotency_key or "", signature, len(body.text))
    except Denied as exc:
        raise exception_for(exc)
    if reservation["cached"]:
        try:
            output = LEDGER.get_cached(reservation)
        except Denied as exc:
            raise exception_for(exc)
        audio_hash = reservation["sha256"]
    else:
        output = await qwen_audio(
            "/api/v1/base/clone",
            {"text": body.text, "language": "Russian",
             "ref_audio_base64": base64.b64encode(reference).decode("ascii"),
             "ref_text": proof["reference_text"],
             "x_vector_only_mode": False,
             "response_format": "wav"},
        )
        receipt = LEDGER.finish(account["id"], x_idempotency_key or "", output)
        audio_hash = receipt["sha256"]
    return Response(
        content=output, media_type="audio/wav",
        headers={"Cache-Control": "no-store", "X-Voice-ID": VOICE_ID,
                 "X-Audio-SHA256": audio_hash,
                 "X-Reference-SHA256": proof["wav_sha256"]},
    )
