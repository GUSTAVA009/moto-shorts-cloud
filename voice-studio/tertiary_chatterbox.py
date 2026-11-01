"""Independent third TTS service: Chatterbox Multilingual V3, Russian.

Run on a THIRD owner-controlled host, never on the factory runner or the
Windows fallback machine. Only the pinned owner-authorized speaker reference
is accepted. No public voice samples, admin, or open generation API.
Install optional model dependencies separately; they are NOT CI requirements.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import re
import wave

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from core import check_wav

VOICE_ID = "gustava-original-v1"
CHANNEL = "gustava"
BACKEND = "chatterbox_multilingual_v3"
KEY_RE = re.compile(r"gvk_[A-Za-z0-9_-]{40,64}\Z")
REQUEST_RE = re.compile(r"[A-Za-z0-9_.:-]{8,96}\Z")
SHA_RE = re.compile(r"[a-f0-9]{64}\Z")

app = FastAPI(title="Private HAPYCH third voice route",
              docs_url=None, redoc_url=None, openapi_url=None)
LOCK = asyncio.Lock()
MODEL = None


class Speech(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=600)
    voice: str
    channel_slug: str
    response_format: str = "wav"


def configured():
    if os.environ.get("GUSTAVA_TERTIARY_TTS_ENABLED") != "1" or (
            os.environ.get("GUSTAVA_TERTIARY_VOICE_CANARY_APPROVED") != "1"):
        raise HTTPException(503,"TERTIARY_VOICE_NOT_APPROVED_OR_ENABLED")
    key = os.environ.get("GUSTAVA_TERTIARY_VOICE_API_KEY", "")
    if not KEY_RE.fullmatch(key):
        raise HTTPException(503,"TERTIARY_VOICE_KEY_NOT_CONFIGURED")
    return key


def authorize(header: str | None):
    key = configured()
    if not header or not header.startswith("Bearer ") or not hmac.compare_digest(
            header[7:], key):
        raise HTTPException(401,"TERTIARY_VOICE_AUTH_REQUIRED")


def reference_path() -> tuple[Path, str]:
    path = Path(os.environ.get("GUSTAVA_TERTIARY_REFERENCE_WAV", "")).expanduser()
    expected = os.environ.get("GUSTAVA_VOICE_REFERENCE_SHA256", "")
    if (not SHA_RE.fullmatch(expected) or
            not str(path) or not path.is_file() or path.suffix.lower() != ".wav"):
        raise HTTPException(503,"TERTIARY_REFERENCE_NOT_INSTALLED")
    try:
        data = path.read_bytes()
        check_wav(data)
    except (ValueError, OSError):
        raise HTTPException(503,"TERTIARY_REFERENCE_UNUSABLE") from None
    if hashlib.sha256(data).hexdigest() != expected:
        raise HTTPException(503,"TERTIARY_REFERENCE_SHA_MISMATCH")
    return path, expected


def _render(text: str, reference: Path) -> bytes:
    """Only this function loads heavy optional Chatterbox/PyTorch packages."""
    global MODEL
    import numpy as np
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    if MODEL is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        MODEL = ChatterboxMultilingualTTS.from_pretrained(device=device,
                                                          t3_model="v3")
    with torch.inference_mode():
        generated = MODEL.generate(text, language_id="ru",
                                   audio_prompt_path=str(reference))
    samples = generated.detach().cpu().float().reshape(-1).numpy()
    if not np.isfinite(samples).all():
        raise ValueError("NON_FINITE_VOICE_AUDIO")
    samples = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(MODEL.sr))
        wav.writeframes(samples.tobytes())
    audio = output.getvalue()
    check_wav(audio)
    return audio


def _cache_paths(request_id: str):
    # No plaintext prompt or API key written to path names or logs.
    root = Path(os.environ.get("GUSTAVA_TERTIARY_CACHE_DIR",
                               "/var/lib/hapych-tertiary-tts")).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    file_id = hashlib.sha256(request_id.encode("utf8")).hexdigest()
    return root / (file_id + ".wav"), root / (file_id + ".json")


@app.post("/v1/audio/speech")
async def speech(body: Speech, authorization: str | None = Header(default=None),
                 x_idempotency_key: str | None = Header(default=None)):
    authorize(authorization)
    if (body.voice != VOICE_ID or body.channel_slug != CHANNEL or
            body.response_format != "wav" or not body.text.strip()):
        raise HTTPException(403,"VOICE_OR_CHANNEL_MISMATCH")
    if not REQUEST_RE.fullmatch(x_idempotency_key or ""):
        raise HTTPException(400,"VALID_IDEMPOTENCY_KEY_REQUIRED")
    reference, reference_sha = reference_path()
    signature = hashlib.sha256(json.dumps(
        body.model_dump(),sort_keys=True,ensure_ascii=False,
        separators=(",",":")).encode("utf8")).hexdigest()
    cache_audio, cache_meta = _cache_paths(x_idempotency_key)
    async with LOCK:
        if cache_audio.is_file() or cache_meta.is_file():
            if not cache_audio.is_file() or not cache_meta.is_file():
                raise HTTPException(503,"TERTIARY_PARTIAL_CACHE_NO_BLIND_RETRY")
            metadata = json.loads(cache_meta.read_text("utf8"))
            raw = cache_audio.read_bytes()
            if (metadata.get("signature") != signature or
                    metadata.get("audio_sha") != hashlib.sha256(raw).hexdigest() or
                    metadata.get("reference_sha") != reference_sha):
                raise HTTPException(409,"TERTIARY_IDEMPOTENCY_CONFLICT")
        else:
            try:
                raw = await asyncio.to_thread(_render,body.text,reference)
            except (RuntimeError, ValueError, OSError):
                # Do not expose model internals or voice-reference path.
                raise HTTPException(502,"TERTIARY_MODEL_GENERATION_FAILED") from None
            metadata = {
                "signature":signature,
                "audio_sha":hashlib.sha256(raw).hexdigest(),
                "reference_sha":reference_sha,
                "backend":BACKEND,
            }
            cache_audio.write_bytes(raw)
            cache_meta.write_text(json.dumps(metadata),encoding="utf8")
    return Response(raw,media_type="audio/wav",headers={
        "X-Voice-ID":VOICE_ID, "X-Channel-ID":CHANNEL,
        "X-Audio-SHA256":metadata["audio_sha"],
        "X-Reference-SHA256":reference_sha,
        "X-TTS-Backend":BACKEND, "Cache-Control":"no-store",
    })


@app.get("/health")
def health(authorization: str | None = Header(default=None)):
    authorize(authorization)
    reference_path()
    return {"ready_for_canonical_request":True,
            "backend":BACKEND,"channel":CHANNEL}
