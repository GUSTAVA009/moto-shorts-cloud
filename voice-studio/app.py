#!/usr/bin/env python3
"""Private owner-only HAPYCH Voice Studio; self-hosted Qwen, never SaaS TTS.

Only the public LOGIN SCREEN is readable without a signed owner session.
The private studio, CSS/JS, health, voice samples, keys and settings require
either the owner session or a strong admin token. The separate TTS endpoint
requires a revocable, per-client 256-bit gvk_ credential.

Do not train on, import, or reproduce recordings of third-party narrators.
"""
from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import subprocess
import tempfile
from pathlib import Path
import re
import secrets
import time
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
import httpx
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from core import (Ledger, VOICE_ID, PRIMARY_CHANNEL, voice_id_for,
                  MAX_INPUT_CHARS, Denied, check_wav, sha)

DATA = Path(os.environ.get("VOICE_STUDIO_DATA", "/data")).resolve()
ROOT = Path(__file__).resolve().parent
DATA.mkdir(parents=True, exist_ok=True)
LEDGER = Ledger(DATA)
VOICE_FILE = DATA / "voice-reference-original.wav"
VOICE_PROOF = DATA / "voice-reference-original.json"
# Oracle Always Free ARM CPU has no GPU. Only use the Qwen3 CustomVoice
# C engine on loopback; never disclose private voice data to public engines.
UPSTREAM=os.environ.get("QWEN_BACKEND_URL","http://127.0.0.1:8002").rstrip("/")

COOKIE = "hapych_owner"
SESSION_HOURS = 8
MAX_LOGINS = 7
LOGIN_WINDOW_SECONDS = 600
LOGIN_ATTEMPTS = {}
TONE_OPTIONS = {
    "deep": "naturally deep and rounded bass-baritone, full-bodied and stable",
    "velvet": "warm smooth baritone, velvety and easy to listen to",
    "resonant": "resonant cinematic low baritone, warm but not artificially lowered",
}
DELIVERY_OPTIONS = {
    "documentary": "confident unhurried documentary storytelling",
    "dynamic": "lively energetic short-form narration, purposeful rhythm",
    "ironic": "light natural irony, expressive but never mocking a real speaker",
}
REFERENCE_TEXT = (
    "Сегодня поговорим о мотоциклах. Иногда самый короткий путь "
    "оказывается самым интересным приключением. Слушай внимательно."
)


def design_instruction(timbre: str, delivery: str):
    if timbre not in TONE_OPTIONS or delivery not in DELIVERY_OPTIONS:
        raise ValueError("VOICE_STYLE_NOT_APPROVED")
    return (
        "Create a completely ORIGINAL fictional male narrator, native Russian "
        "with precise Russian pronunciation and clearly articulated consonants. "
        + TONE_OPTIONS[timbre] + "; " + DELIVERY_OPTIONS[delivery]
        + ". Natural expressiveness and pauses, single voice, no pitch shifting. "
        "Do not imitate any identifiable real person, performer, or vendor voice."
    )


ORIGINAL_INSTRUCTION = design_instruction("deep", "documentary")

app = FastAPI(
    title="HAPYCH Voice — owner-only free ARM cloud service", version="0.3.0",
    description="Owner-only original Russian TTS; API requires revocable owner-issued keys",
    docs_url=None, redoc_url=None, openapi_url=None,
)
INFERENCE_LOCK = asyncio.Lock()
DESIGN_LOCK = asyncio.Lock()


def configured_secret(name: str, length: int = 32):
    value = os.environ.get(name, "")
    if len(value) < length or value.startswith("REPLACE_"):
        raise HTTPException(503, "OWNER_AUTH_CONFIGURATION_REQUIRED")
    return value


def owner_cookie(payload: str, secret: str):
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return payload + "." + digest


def owner_session(request: Request):
    raw = request.cookies.get(COOKIE, "")
    pieces = raw.split(".")
    if len(pieces) != 3:
        return None
    nonce, expires, signature = pieces
    if (not re.fullmatch(r"[A-Za-z0-9_-]{20,64}", nonce)
            or not re.fullmatch(r"[0-9]{10,12}", expires)
            or int(expires) < int(time.time())):
        return None
    try:
        secret = configured_secret("VOICE_STUDIO_SESSION_SECRET", 40)
    except HTTPException:
        return None
    payload = nonce + "." + expires
    expected = owner_cookie(payload, secret)
    if not hmac.compare_digest(raw, expected):
        return None
    return payload


def csrf_for(payload: str):
    secret = configured_secret("VOICE_STUDIO_SESSION_SECRET", 40)
    return hmac.new(secret.encode(), ("csrf:" + payload).encode(),
                    hashlib.sha256).hexdigest()


def admin(request: Request, x_admin_token: str | None = Header(default=None),
          x_csrf_token: str | None = Header(default=None)):
    # CLI administrators with explicit strong X-Admin-Token can administer
    # without a cookie; browsers never store an admin secret after login.
    if x_admin_token:
        expected = configured_secret("VOICE_STUDIO_ADMIN_TOKEN")
        if not hmac.compare_digest(x_admin_token, expected):
            raise HTTPException(401, "OWNER_AUTH_REQUIRED")
        return True
    session = owner_session(request)
    if session is None:
        raise HTTPException(401, "OWNER_AUTH_REQUIRED")
    if request.method not in ("GET", "HEAD"):
        expected = csrf_for(session)
        if not x_csrf_token or not hmac.compare_digest(x_csrf_token, expected):
            raise HTTPException(403, "OWNER_CSRF_VALIDATION_REQUIRED")
    return True


def safe_upstream():
    parsed=urlsplit(UPSTREAM)
    if (parsed.scheme!="http" or parsed.hostname not in
            {"127.0.0.1","localhost"}
            or parsed.port!=8002 or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path):
        raise RuntimeError("QWEN_CPU_ENGINE_MUST_BE_LOOPBACK_8002")


def adjust_speed(source:bytes, speed:float):
    """CPU postprocessing with ffmpeg atempo preserves voice pitch."""
    if speed==1.0:
        return source
    # Never run a shell. Input/output live only in the private data folder.
    with tempfile.TemporaryDirectory(prefix="pace-",dir=DATA) as td:
        incoming=Path(td)/"input.wav"
        outgoing=Path(td)/"output.wav"
        incoming.write_bytes(source)
        try:
            subprocess.run([
                "ffmpeg","-nostdin","-hide_banner","-loglevel","error",
                "-y","-i",str(incoming),"-filter:a",f"atempo={speed:.3f}",
                "-ar","24000","-ac","1","-c:a","pcm_s16le",str(outgoing)
            ],check=True,capture_output=True,timeout=60)
        except (subprocess.CalledProcessError,subprocess.TimeoutExpired,
                FileNotFoundError):
            raise HTTPException(502,"VOICE_PACE_PROCESSING_FAILED") from None
        result=outgoing.read_bytes()
        try:check_wav(result)
        except ValueError:
            raise HTTPException(502,"VOICE_PACE_INVALID_AUDIO") from None
        return result


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=256)


class CreateKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=2, max_length=72)
    # 0 = unlimited locally; no credits or quota from external TTS providers.
    max_chars_month: int = Field(default=0, ge=0, le=100_000_000)
    max_rpm: int = Field(default=12, ge=1, le=120)
    channel_slug: str = PRIMARY_CHANNEL


class ChannelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(min_length=3,max_length=40)
    name: str = Field(min_length=2,max_length=72)
    youtube_channel_id: str | None = None
    timbre: Literal["deep","velvet","resonant"] = "deep"
    delivery: Literal["documentary","dynamic","ironic"] = "documentary"


class OriginalDesign(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_original: bool
    timbre: Literal["deep", "velvet", "resonant"] = "deep"
    delivery: Literal["documentary", "dynamic", "ironic"] = "documentary"
    channel_slug: str = PRIMARY_CHANNEL


class SpeechBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)
    voice: str = VOICE_ID
    channel_slug: str | None = None
    speed: float = Field(default=1.0, ge=0.85, le=1.15)
    response_format: str = "wav"


def exception_for(error: Denied):
    return HTTPException(error.status, str(error))


def voice_paths(slug: str):
    """Per-channel immutable voice references; no traversal across tenants."""
    LEDGER.get_channel(slug)
    if slug == PRIMARY_CHANNEL:
        return VOICE_FILE, VOICE_PROOF
    directory=DATA / "voices" / slug
    return directory / "reference-original.wav", directory / "reference-original.json"


def validated_reference(slug: str = PRIMARY_CHANNEL):
    voice_file,voice_proof=voice_paths(slug)
    if not voice_file.is_file() or not voice_proof.is_file():
        raise HTTPException(503,"ORIGINAL_VOICE_NOT_CREATED")
    try:
        meta=json.loads(voice_proof.read_text(encoding="utf8"))
        raw=voice_file.read_bytes()
        check_wav(raw)
        design=meta.get("design",{"timbre":"deep","delivery":"documentary"})
        expected=design_instruction(design["timbre"],design["delivery"])
        valid=(
            meta.get("source")=="selfhosted_qwen_cpu_preset"
            and meta.get("channel_slug",PRIMARY_CHANNEL)==slug
            and meta.get("voice_id")==voice_id_for(slug)
            and meta.get("wav_sha256")==sha(raw)
            and meta.get("reference_text")==REFERENCE_TEXT
            and meta.get("instruction_sha256")==sha(expected.encode("utf8"))
            and meta.get("preset_voice")==LEDGER.get_channel(slug)["speaker_preset"]
        )
        if not valid:
            raise ValueError("reference fingerprint mismatch")
        return raw,meta
    except (ValueError,OSError,TypeError,KeyError,json.JSONDecodeError):
        raise HTTPException(503,"ORIGINAL_VOICE_REFERENCE_VERIFICATION_FAILED")


async def qwen_audio(route: str,payload:dict):
    """Use official Qwen3 C CustomVoice HTTP endpoint, not cloud SaaS."""
    safe_upstream()
    if route not in ("/api/v1/voice-design/generate","/api/v1/base/clone"):
        raise RuntimeError("QWEN_UNAPPROVED_OPERATION")
    # Input is a private, server-owned Qwen3 speaker preset, NOT a model
    # created by VoiceDesign. CPU 0.6B does not implement VoiceDesign.
    speaker=payload.get("speaker")
    from core import FREE_CPU_SPEAKERS
    if speaker not in FREE_CPU_SPEAKERS:
        raise HTTPException(422,"CHANNEL_CPU_VOICE_NOT_ALLOCATED")
    body={"text":payload["text"],"speaker":speaker,"language":"Russian"}
    timeout=httpx.Timeout(connect=8,read=600,write=25,pool=15)
    async with INFERENCE_LOCK:
        try:
            async with httpx.AsyncClient(timeout=timeout,
                                         follow_redirects=False,
                                         trust_env=False) as client:
                response=await client.post(UPSTREAM+"/v1/tts",json=body,
                                            headers={"Accept":"audio/wav"})
        except (httpx.TimeoutException,httpx.RequestError):
            raise HTTPException(502,"PRIVATE_CPU_VOICE_ENGINE_UNAVAILABLE") from None
    if response.status_code!=200:
        raise HTTPException(502,"PRIVATE_CPU_VOICE_ENGINE_FAILED")
    try: check_wav(response.content)
    except ValueError:
        raise HTTPException(502,"PRIVATE_CPU_VOICE_ENGINE_INVALID_WAV") from None
    speed=payload.get("speed",1.0)
    if not isinstance(speed,(int,float)) or not .80<=speed<=1.20:
        raise HTTPException(422,"VOICE_PACE_OUTSIDE_SAFE_RANGE")
    return adjust_speed(response.content,float(speed))


@app.middleware("http")
async def guard_private_site(request: Request, call_next):
    path = request.url.path
    private = (path in ("/", "/site.css", "/site.js", "/health")
               or path.startswith("/api/admin/"))
    # Public login screen and service endpoint have their own exact credentials.
    if private and path not in ("/api/admin/keys", "/api/admin/voice"):
        # All admin routes are validated by their Depends(admin), including
        # CLI X-Admin-Token. Do not prematurely reject that admin path here.
        if not path.startswith("/api/admin/") and owner_session(request) is None:
            if path == "/":
                return RedirectResponse("/login", status_code=303)
            return JSONResponse({"detail": "OWNER_AUTH_REQUIRED"}, status_code=401)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; "
        "object-src 'none'; frame-ancestors 'none'; base-uri 'none'; "
        "form-action 'self'")
    return response


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if owner_session(request):
        return RedirectResponse("/", status_code=303)
    return (ROOT / "login.html").read_text(encoding="utf8")


@app.get("/login.css")
def login_style():
    return FileResponse(ROOT / "login.css", media_type="text/css")


@app.get("/login.js")
def login_script():
    return FileResponse(ROOT / "login.js", media_type="application/javascript")


@app.post("/auth/login")
def login(body: LoginBody, request: Request, response: Response):
    client_ip = str(request.client.host if request.client else "unknown")
    now = int(time.time())
    attempts = [x for x in LOGIN_ATTEMPTS.get(client_ip, [])
                if x >= now - LOGIN_WINDOW_SECONDS]
    if len(attempts) >= MAX_LOGINS:
        raise HTTPException(429, "OWNER_LOGIN_RATE_LIMIT")
    expected = configured_secret("VOICE_STUDIO_ADMIN_TOKEN")
    if not hmac.compare_digest(body.password, expected):
        attempts.append(now)
        LOGIN_ATTEMPTS[client_ip] = attempts
        raise HTTPException(401, "INVALID_OWNER_ACCESS")
    LOGIN_ATTEMPTS.pop(client_ip, None)
    nonce = secrets.token_urlsafe(24)
    payload = nonce + "." + str(now + SESSION_HOURS * 3600)
    session = owner_cookie(
        payload, configured_secret("VOICE_STUDIO_SESSION_SECRET", 40))
    response.set_cookie(
        COOKIE, session, max_age=SESSION_HOURS*3600, path="/",
        httponly=True, samesite="strict",
        secure=os.environ.get("VOICE_STUDIO_LOCAL_HTTP") != "1",
    )
    return {"ok": True, "expires_in_seconds": SESSION_HOURS * 3600}


@app.get("/auth/session")
def session_info(request: Request):
    payload = owner_session(request)
    if not payload:
        raise HTTPException(401, "OWNER_AUTH_REQUIRED")
    return {"authenticated": True, "csrf": csrf_for(payload)}


@app.post("/auth/logout", dependencies=[Depends(admin)])
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict",
                           secure=os.environ.get("VOICE_STUDIO_LOCAL_HTTP") != "1")
    return {"ok": True}


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
    return {
        "status": "web_api_running_not_gpu_verified",
        "engine": "qwen3-tts-selfhosted", "voice_id": VOICE_ID,
        "reference_available": VOICE_FILE.is_file() and VOICE_PROOF.is_file(),
        "audio_generated": False,
    }


@app.get("/api/admin/channels", dependencies=[Depends(admin)])
def channels():
    return {"channels":LEDGER.list_channels()}


@app.post("/api/admin/channels", dependencies=[Depends(admin)], status_code=201)
def create_channel(body: ChannelCreate):
    try:
        return LEDGER.create_channel(
            body.slug,body.name,body.timbre,body.delivery,
            body.youtube_channel_id)
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from None
    except Denied as exc:
        raise exception_for(exc) from None


@app.get("/api/admin/keys", dependencies=[Depends(admin)])
def keys(channel_slug: str | None = None):
    try:
        return {"keys":LEDGER.list_keys(channel_slug)}
    except Denied as exc:
        raise exception_for(exc) from None
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from None


@app.post("/api/admin/keys", dependencies=[Depends(admin)], status_code=201)
def create_key(body: CreateKey):
    try:
        return LEDGER.create_key(body.label, body.max_chars_month,
                                 body.max_rpm, body.channel_slug)
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from None
    except Denied as exc:
        raise exception_for(exc) from None


@app.delete("/api/admin/keys/{key_id}", dependencies=[Depends(admin)])
def revoke_key(key_id: int):
    try:
        LEDGER.revoke(key_id)
    except Denied as exc:
        raise exception_for(exc) from None
    return {"revoked": True, "id": key_id}


@app.get("/api/admin/voice", dependencies=[Depends(admin)])
def voice_details(channel_slug: str = PRIMARY_CHANNEL):
    try:
        ch=LEDGER.get_channel(channel_slug)
    except Denied as exc:
        raise exception_for(exc) from None
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from None
    vf,vp=voice_paths(channel_slug)
    if not vf.is_file() and not vp.is_file():
        return {"created":False, "channel_slug":channel_slug,
                "voice_id":ch["voice_id"],
                "design":{"timbre":ch["voice_timbre"],
                          "delivery":ch["voice_delivery"]}}
    _,meta=validated_reference(channel_slug)
    return {
        "created":True,"channel_slug":channel_slug,
        "voice_id":ch["voice_id"],"created_at":meta.get("created_at"),
        "reference_sha256":meta["wav_sha256"],"source":meta["source"],
        "design":meta.get("design",{"timbre":"deep","delivery":"documentary"}),
    }


@app.get("/api/admin/voice/reference", dependencies=[Depends(admin)])
def original_reference(channel_slug: str = PRIMARY_CHANNEL):
    raw, meta = validated_reference(channel_slug)
    return Response(content=raw, media_type="audio/wav",
                    headers={"X-Voice-SHA256": meta["wav_sha256"]})


@app.post("/api/admin/voice/design", dependencies=[Depends(admin)])
async def create_original(body: OriginalDesign):
    if body.confirm_original is not True:
        raise HTTPException(400,"CONFIRM_PERMITTED_OPEN_MODEL_SPEAKER")
    async with DESIGN_LOCK:
        try:
            channel=LEDGER.get_channel(body.channel_slug)
        except Denied as exc:
            raise exception_for(exc) from None
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from None
        voice_file,voice_proof=voice_paths(body.channel_slug)
        if voice_file.exists() or voice_proof.exists():
            raise HTTPException(409,"ORIGINAL_VOICE_IS_PINNED_DO_NOT_OVERWRITE")
        # Before the first original reference exists, the owner may choose
        # the voice's timbre and delivery. After creation, SHA-pinned proof
        # makes the channel voice immutable.
        with LEDGER.connection() as db:
            db.execute(
                "UPDATE channels SET voice_timbre=?,voice_delivery=? "
                "WHERE slug=?",
                (body.timbre,body.delivery,body.channel_slug))
        instruction=design_instruction(body.timbre,body.delivery)
        # On a free cloud CPU, create a pinned ORIGINAL-FOR-THIS-CHANNEL
        # sample of a licensed open-model voice preset; NOT a new designed
        # timbre. It must not be marketed as an exclusive original speaker.
        speaker=channel["speaker_preset"]
        generated=await qwen_audio(
            "/api/v1/voice-design/generate",
            {"text":REFERENCE_TEXT,"language":"Russian","speaker":speaker,
             "instruct":instruction,"response_format":"wav"},
        )
        proof = {
            "source":"selfhosted_qwen_cpu_preset",
            "preset_voice":speaker,
            "channel_slug":body.channel_slug,
            "voice_id":voice_id_for(body.channel_slug),
            "reference_text": REFERENCE_TEXT,
            "instruction_sha256": sha(instruction.encode("utf8")),
            "design": {"timbre": body.timbre, "delivery": body.delivery},
            "wav_sha256": sha(generated),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "model_expected":"Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
            "exclusive_original_voice":False,
            "derived_from_cartesia":False,
        }
        try:
            voice_file.parent.mkdir(parents=True,exist_ok=True)
            with voice_file.open("xb") as output:
                output.write(generated)
            with voice_proof.open("x", encoding="utf8") as output:
                json.dump(proof, output, ensure_ascii=False, indent=2)
        except FileExistsError:
            raise HTTPException(
                409, "ORIGINAL_VOICE_IS_PINNED_DO_NOT_OVERWRITE") from None
        return {
            "voice_id":voice_id_for(body.channel_slug),
            "channel_slug":body.channel_slug,"created":True,
            "reference_sha256": proof["wav_sha256"],
            "next":"Review preset's native Russian speech before publishing",
        }


@app.post("/v1/audio/speech")
async def speech(
    body: SpeechBody, authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    x_idempotency_key: str | None = Header(default=None),
):
    token = x_api_key or (
        authorization.split(" ", 1)[1]
        if authorization and authorization.startswith("Bearer ") else None)
    try:
        account = LEDGER.authenticate(token or "")
    except Denied as exc:
        raise exception_for(exc) from None
    slug=account["channel_slug"]
    actual_voice=voice_id_for(slug)
    if body.voice != actual_voice or (
            body.channel_slug is not None and body.channel_slug != slug):
        raise HTTPException(403,"API_KEY_IS_BOUND_TO_ANOTHER_CHANNEL_VOICE")
    if body.response_format != "wav":
        raise HTTPException(400, "ONLY_WAV_SUPPORTED_FOR_VERIFIED_RAW_AUDIO")
    if not body.text.strip():
        raise HTTPException(400, "EMPTY_TRANSCRIPT")
    reference,proof=validated_reference(slug)
    signature=sha(json.dumps({
        "text":body.text,"voice":actual_voice,"channel_slug":slug,
        "speed": body.speed, "response_format": "wav",
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf8"))
    try:
        reservation = LEDGER.reserve(
            account, x_idempotency_key or "", signature, len(body.text))
    except Denied as exc:
        raise exception_for(exc) from None
    if reservation["cached"]:
        try:
            output = LEDGER.get_cached(reservation)
        except Denied as exc:
            raise exception_for(exc) from None
        audio_hash = reservation["sha256"]
    else:
        output = await qwen_audio(
            "/api/v1/base/clone", {
                "text": body.text, "language": "Russian",
                "speaker":proof["preset_voice"],
                "ref_audio_base64":base64.b64encode(reference).decode("ascii"),
                "ref_text":proof["reference_text"],
                "x_vector_only_mode":False,"speed":body.speed,
                "response_format": "wav",
            },
        )
        receipt = LEDGER.finish(account["id"], x_idempotency_key or "", output)
        audio_hash = receipt["sha256"]
    return Response(
        content=output, media_type="audio/wav",
        headers={"X-Voice-ID":actual_voice,"X-Channel-ID":slug,
                 "X-Audio-SHA256":audio_hash,
                 "X-Reference-SHA256":proof["wav_sha256"]},
    )
