"""The YouTube factory's own self-hosted Qwen3 Voice Studio provider.

No Cartesia or third-party TTS billing. The provider MUST use HTTPS to the
exact approved hostname, a secret 256-bit gvk_ key, a pinned original voice,
and an approved reference WAV SHA-256. No redirect, no voice substitutions,
no blind retries on an uncertain source request.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import wave

from deep_voice import pcm_stats, provenance_path

VOICE_ENGINE = "gustava_selfhosted_qwen3"
VOICE_ID = "gustava-original-v1"
PROFILE_ID = "gustava_original_qwen3_v1"
MAX_BYTES = 12_000_000


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def approved_profile(episode):
    return bool(episode.get("voice_engine") == VOICE_ENGINE
                and episode.get("voice_profile") == PROFILE_ID
                and episode.get("selfhosted_voice_id") == VOICE_ID)


def valid_url(env=None):
    env = os.environ if env is None else env
    url = str(env.get("GUSTAVA_VOICE_API_URL") or "")
    approved_host = str(env.get("GUSTAVA_VOICE_APPROVED_HOST") or "").strip().lower()
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https"
            or not approved_host or not re.fullmatch(
                r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", approved_host)
            or parsed.hostname != approved_host
            or parsed.path != "/v1/audio/speech"
            or parsed.query or parsed.fragment
            or parsed.username or parsed.password or
            parsed.port not in (None,443)):
        raise ValueError("SELFHOSTED_TTS_UNAPPROVED_HTTPS_HOST")
    return url


def ready(episode, environment=None):
    env = os.environ if environment is None else environment
    if not approved_profile(episode) or episode.get("auto_publish") is True:
        return False
    if not (env.get("GUSTAVA_SELFHOSTED_TTS_ENABLED") == "1"
            and (env.get("GUSTAVA_VOICE_KEY_PRESENT") == "true" or
                 bool(env.get("GUSTAVA_VOICE_API_KEY")))
            and re.fullmatch(r"[0-9a-f]{64}",
                             str(env.get("GUSTAVA_VOICE_REFERENCE_SHA256") or ""))):
        return False
    try:
        valid_url(env)
    except (ValueError, TypeError):
        return False
    return True


def valid_source_wav(raw):
    if not isinstance(raw, bytes) or len(raw) < 10000 or len(raw) > MAX_BYTES:
        raise ValueError("SELFHOSTED_TTS_WAV_INVALID_SIZE")
    try:
        with wave.open(__import__("io").BytesIO(raw),"rb") as f:
            params=(f.getnchannels(),f.getsampwidth(),f.getframerate())
            duration=f.getnframes()/f.getframerate()
            count=f.getnframes()
    except (ValueError,EOFError,ZeroDivisionError,wave.Error) as exc:
        raise ValueError("SELFHOSTED_TTS_INVALID_WAV_HEADER") from exc
    if (params[0:2] != (1,2)
            or not 12000 <= params[2] <= 48000
            or not 3.0 <= duration <= 35.0
            or len(raw) < count*2+40):
        raise ValueError("SELFHOSTED_TTS_UNSUITABLE_AUDIO_DURATION_OR_FORMAT")
    return round(duration,3)


def _request(episode):
    env=os.environ
    url=valid_url(env)
    token=env.get("GUSTAVA_VOICE_API_KEY","")
    if not re.fullmatch(r"gvk_[A-Za-z0-9_-]{40,64}",token):
        raise RuntimeError("SELFHOSTED_TTS_KEY_NOT_INSTALLED")
    if env.get("GUSTAVA_SELFHOSTED_TTS_ENABLED") != "1":
        raise RuntimeError("SELFHOSTED_TTS_NOT_ENABLED")
    text=episode["narration"]
    request_id=(episode["id"]+"-"+sha(text.encode("utf8"))[:20])
    payload={
        "text": text, "voice": VOICE_ID, "response_format":"wav"
    }
    req=urllib.request.Request(url,
        data=json.dumps(payload,ensure_ascii=False).encode("utf8"),
        headers={
            "Authorization":"Bearer "+token,
            "Content-Type":"application/json",
            "Accept":"audio/wav",
            "X-Idempotency-Key":request_id,
            "User-Agent":"GUSTAVA-SHORTS-FACTORY",
        },method="POST")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):
            return None
    try:
        # Refuse redirects so Authorization never leaves the approved domain.
        with urllib.request.build_opener(NoRedirect()).open(
                req,timeout=360) as response:
            if response.geturl() != url:
                raise RuntimeError("SELFHOSTED_TTS_REDIRECT_BLOCKED")
            data=response.read(MAX_BYTES+1)
            generated_sha=response.headers.get("X-Audio-SHA256","")
            voice_id=response.headers.get("X-Voice-ID","")
            ref_sha=response.headers.get("X-Reference-SHA256","")
    except urllib.error.HTTPError as error:
        # Never include provider URL, headers, response body or token.
        raise RuntimeError("SELFHOSTED_TTS_HTTP_"+str(error.code)) from None
    except urllib.error.URLError:
        raise RuntimeError("SELFHOSTED_TTS_NETWORK_UNAVAILABLE") from None
    valid_source_wav(data)
    if (generated_sha != sha(data)
            or voice_id != VOICE_ID
            or ref_sha != env.get("GUSTAVA_VOICE_REFERENCE_SHA256")):
        raise ValueError("SELFHOSTED_TTS_SOURCE_OR_SPEAKER_SHA_MISMATCH")
    return data,ref_sha


def verify_profile(wav,episode):
    if not approved_profile(episode):
        raise ValueError("SELFHOSTED_VOICE_PROFILE_NOT_PINNED")
    audio=Path(wav)
    sidecar=provenance_path(audio)
    if not sidecar.is_file() or not audio.is_file():
        raise ValueError("SELFHOSTED_VOICE_PROVENANCE_MISSING")
    report=json.loads(sidecar.read_text(encoding="utf8"))
    expected={
        "episode_id":episode["id"],
        "voice_engine":VOICE_ENGINE,
        "voice_profile":PROFILE_ID,
        "voice_id":VOICE_ID,
        "text_sha256":sha(episode["narration"].encode("utf8")),
        "wav_sha256":sha(audio.read_bytes()),
    }
    if any(report.get(k) != v for k,v in expected.items()):
        raise ValueError("SELFHOSTED_VOICE_PROVENANCE_MISMATCH")
    if not all(re.fullmatch(r"[0-9a-f]{64}",str(report.get(k) or ""))
               for k in ("source_audio_sha256","reference_sha256")):
        raise ValueError("SELFHOSTED_VOICE_SOURCE_SHA_NOT_PINNED")
    stats=pcm_stats(audio)
    if abs(stats["duration_seconds"]-report.get("duration_seconds",-1))>.02:
        raise ValueError("SELFHOSTED_VOICE_DURATION_MISMATCH")
    return report


def render(episode,destination,requester=None):
    if not approved_profile(episode):
        raise ValueError("SELFHOSTED_VOICE_NOT_AUTHORIZED")
    target=Path(destination)
    if target.is_file() or provenance_path(target).is_file():
        return verify_profile(target,episode)["duration_seconds"]
    if os.environ.get("GUSTAVA_SELFHOSTED_TTS_ENABLED") != "1":
        raise RuntimeError("SELFHOSTED_TTS_NOT_ENABLED")
    source,ref_sha=(requester or _request)(episode)
    valid_source_wav(source)
    if ref_sha != os.environ.get("GUSTAVA_VOICE_REFERENCE_SHA256"):
        raise ValueError("SELFHOSTED_TTS_REFERENCE_NOT_APPROVED")
    target.parent.mkdir(parents=True,exist_ok=True)
    raw=target.with_name(target.stem+".source.wav")
    temp=target.with_name(target.stem+".converted.wav")
    try:
        raw.write_bytes(source)
        subprocess.run([
            "ffmpeg","-hide_banner","-nostdin","-loglevel","error",
            "-y","-i",str(raw),"-vn","-ac","1","-ar","24000",
            "-c:a","pcm_s16le",str(temp)
        ],check=True,capture_output=True,timeout=120)
        info=pcm_stats(temp)
        temp.replace(target)
        proof={
            "episode_id":episode["id"],"voice_engine":VOICE_ENGINE,
            "voice_profile":PROFILE_ID,"voice_id":VOICE_ID,
            "text_sha256":sha(episode["narration"].encode("utf8")),
            "source_audio_sha256":sha(source),
            "reference_sha256":ref_sha,
            "wav_sha256":sha(target.read_bytes()),
            "duration_seconds":info["duration_seconds"],
            "local_selfhosted":True,"voice_layers":1,"pitch_shift":1.0,
        }
        provenance_path(target).write_text(
            json.dumps(proof,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
        verify_profile(target,episode)
        print("GUSTAVA_SELFHOSTED_PRIVATE_AUDIO_READY",episode["id"],
              info["duration_seconds"],flush=True)
        return info["duration_seconds"]
    finally:
        raw.unlink(missing_ok=True)
        temp.unlink(missing_ok=True)
