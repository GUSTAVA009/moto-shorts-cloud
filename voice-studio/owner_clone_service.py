"""Private CPU Qwen3 narrator with GitHub Actions OIDC, no SaaS TTS key.

Designed for an isolated Linux server behind a Cloudflare named tunnel:
* HTTP is bound strictly to loopback, no public app listening on the VPS.
* A GitHub OIDC ID token is accepted only from the exact owner repository,
  main branch, the designated render workflow and a fixed audience.
* Owner gvk_ token is optional for private testing; never logged.
* A fixed private 30-second voice reference WAV is SHA pinned, never uploaded.
* Real model output, amplitude, duration and SHA checks, idempotent cache.
* No audio means no success. No cloud fees or environment-wide pip installs.
"""
from __future__ import annotations

import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import re
import resource
import subprocess
import tempfile
import threading
import time
import wave

CHANNEL = "gustava"
VOICE_ID = "gustava-original-v1"
AUDIENCE = "voice.hapychrust.ru"
REPO_NAME = "GUSTAVA009/moto-shorts-cloud"
REPO_ID = "1436068497"
REQUIRED_REF = "refs/heads/main"
ALLOWED_WORKFLOWS = (
    "GUSTAVA009/moto-shorts-cloud/.github/workflows/daily-preview.yml@refs/heads/main",
    "GUSTAVA009/moto-shorts-cloud/.github/workflows/render-new-short.yml@refs/heads/main",
)
TOKEN_RE = re.compile(r"gvk_[A-Za-z0-9_-]{40,64}\Z")
REQ_RE = re.compile(r"[A-Za-z0-9_.:-]{8,96}\Z")
SHA_RE = re.compile(r"[a-f0-9]{64}\Z")
MAX_BODY = 3500
MAX_WAV = 12_000_000
LOCK = threading.Lock()
JWK_CLIENT = None


def required_env(name):
    v = str(os.environ.get(name) or "")
    if not v.strip():
        raise RuntimeError("OWNER_TTS_MISSING_" + name)
    return v


def paths():
    root = Path(required_env("OWNER_TTS_ROOT")).resolve()
    if not root.is_dir():
        raise RuntimeError("OWNER_TTS_ROOT_NOT_INSTALLED")
    engine = root / "engine" / "qwen_tts"
    model = root / "engine" / "qwen3-tts-0.6b-base"
    ref = root / "private" / "owner-approved-deep-reference.wav"
    if not engine.is_file() or not model.is_dir() or not ref.is_file():
        raise RuntimeError("OWNER_TTS_MODEL_OR_REFERENCE_UNAVAILABLE")
    expected = required_env("GUSTAVA_VOICE_REFERENCE_SHA256")
    if not SHA_RE.fullmatch(expected):
        raise RuntimeError("OWNER_TTS_REFERENCE_SHA_NOT_PINNED")
    if hashlib.sha256(ref.read_bytes()).hexdigest() != expected:
        raise RuntimeError("OWNER_TTS_REFERENCE_SHA_CHANGED")
    return root, engine, model, ref, expected


def validate_actions_claims(claims):
    """Never accept token from an unrelated fork, branch or job."""
    if (str(claims.get("repository_id")) != REPO_ID
            or claims.get("repository") != REPO_NAME
            or claims.get("ref") != REQUIRED_REF
            or claims.get("workflow_ref") not in ALLOWED_WORKFLOWS):
        raise PermissionError("OWNER_TTS_GITHUB_WORKFLOW_NOT_AUTHORIZED")
    return True


def actions_oidc(token):
    """Verify GitHub's RS256 signature and standard issuer, exp, aud, nbf."""
    if os.environ.get("OWNER_TTS_ALLOW_GITHUB_OIDC") != "1":
        raise PermissionError("OWNER_TTS_GITHUB_OIDC_NOT_ENABLED")
    if len(token) > 6500 or len(token.split(".")) != 3:
        raise PermissionError("OWNER_TTS_INVALID_GITHUB_TOKEN")
    try:
        import jwt
        from jwt import PyJWKClient
        global JWK_CLIENT
        if JWK_CLIENT is None:
            JWK_CLIENT = PyJWKClient(
                "https://token.actions.githubusercontent.com/.well-known/jwks",
                cache_keys=True, lifespan=300, timeout=10)
        key = JWK_CLIENT.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token, key=key.key, algorithms=["RS256"],
            audience=AUDIENCE, issuer="https://token.actions.githubusercontent.com",
            options={"require":["iss","aud","exp","iat","sub","nbf"]},
            leeway=20)
        validate_actions_claims(claims)
    except Exception:
        # No raw JWT, headers, paths, or claim body in any public error.
        raise PermissionError("OWNER_TTS_INVALID_GITHUB_IDENTITY") from None


def authorize(header):
    if not isinstance(header, str) or not header.startswith("Bearer "):
        raise PermissionError("OWNER_TTS_BEARER_REQUIRED")
    token = header[7:]
    secret = str(os.environ.get("OWNER_TTS_API_KEY") or "")
    if TOKEN_RE.fullmatch(secret) and hmac.compare_digest(token, secret):
        return "owner_key"
    actions_oidc(token)
    return "github_actions"


def validate_request(obj, request_id):
    if not isinstance(obj, dict) or not REQ_RE.fullmatch(request_id or ""):
        raise ValueError("OWNER_TTS_IDEMPOTENCY_KEY_REQUIRED")
    if set(obj) != {"text","voice","channel_slug","response_format"}:
        raise ValueError("OWNER_TTS_INVALID_REQUEST_SHAPE")
    text = obj.get("text")
    if not isinstance(text,str) or not 15 <= len(text.strip()) <= 600:
        raise ValueError("OWNER_TTS_INVALID_TRANSCRIPT")
    if (obj.get("voice") != VOICE_ID or obj.get("channel_slug") != CHANNEL
            or obj.get("response_format") != "wav"):
        raise PermissionError("OWNER_TTS_VOICE_CHANNEL_MISMATCH")
    return text


def wav_checked(raw):
    if not isinstance(raw,bytes) or not 10000 <= len(raw) <= MAX_WAV:
        raise ValueError("OWNER_TTS_AUDIO_SIZE_REJECTED")
    with wave.open(io.BytesIO(raw),"rb") as w:
        if w.getnchannels()!=1 or w.getsampwidth()!=2 or w.getframerate()!=24000:
            raise ValueError("OWNER_TTS_AUDIO_NOT_PCM16_MONO_24KHZ")
        n = w.getnframes()
        duration = n / w.getframerate()
        pcm = w.readframes(n)
    if not 3.0 <= duration <= 35.0 or len(pcm) != n*2:
        raise ValueError("OWNER_TTS_AUDIO_DURATION_OR_TRUNCATION")
    if max(abs(int.from_bytes(pcm[i:i+2],"little",signed=True))
           for i in range(0,min(len(pcm),409600),200)) < 150:
        raise ValueError("OWNER_TTS_AUDIO_SILENT")
    return duration


def production_run(text, output_path, root, engine, model, reference):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    cmd = [str(engine), "-d", str(model), "--ref-audio", str(reference),
           "--int8", "-j", "2", "-l", "Russian",
           "--text", text, "-o", str(output_path)]
    def limits():
        os.nice(12)
        resource.setrlimit(resource.RLIMIT_AS,(6_200_000_000,6_200_000_000))
    result = subprocess.run(cmd, cwd=root/"engine", env=env,
                            timeout=330, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, preexec_fn=limits)
    if result.returncode:
        raise RuntimeError("OWNER_TTS_CPU_ENGINE_FAILED")
    if not output_path.is_file():
        raise RuntimeError("OWNER_TTS_NO_OUTPUT_FILE")
    raw = output_path.read_bytes()
    wav_checked(raw)
    return raw


def build_audio(obj, request_id, producer=production_run):
    text = validate_request(obj, request_id)
    root, engine, model, reference, ref_sha = paths()
    private = root / "private"
    cache = private / "request_cache"
    cache.mkdir(mode=0o700,parents=True,exist_ok=True)
    signature = hashlib.sha256(
        json.dumps(obj,sort_keys=True,ensure_ascii=False,
                   separators=(",",":")).encode("utf-8")).hexdigest()
    key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
    target, meta = cache/(key+".wav"), cache/(key+".json")
    with LOCK:
        if target.exists() or meta.exists():
            if not target.is_file() or not meta.is_file():
                raise RuntimeError("OWNER_TTS_PARTIAL_CACHE_REQUIRES_REVIEW")
            previous=json.loads(meta.read_text(encoding="utf-8"))
            raw=target.read_bytes()
            if (previous.get("signature")!=signature or
                    previous.get("audio_sha")!=hashlib.sha256(raw).hexdigest()
                    or previous.get("reference_sha")!=ref_sha):
                raise ValueError("OWNER_TTS_IDEMPOTENCY_COLLISION")
            wav_checked(raw)
            return raw,ref_sha
        fd,tmp=tempfile.mkstemp(prefix="speech-",suffix=".wav",dir=cache)
        os.close(fd)
        tmp=Path(tmp)
        try:
            raw=producer(text,tmp,root,engine,model,reference)
            wav_checked(raw)
            tmp.write_bytes(raw)
            tmp.replace(target)
            metadata={"signature":signature,
                      "audio_sha":hashlib.sha256(raw).hexdigest(),
                      "reference_sha":ref_sha,
                      "created_at_unix":int(time.time())}
            metadata_tmp=meta.with_suffix(".json.tmp")
            metadata_tmp.write_text(json.dumps(metadata),encoding="utf-8")
            metadata_tmp.replace(meta)
            return raw,ref_sha
        finally:
            tmp.unlink(missing_ok=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "HAPYCH-Voice/1.0"
    sys_version = ""
    def log_message(self,fmt,*args):
        # Do not log spoken prompts, tokens, references, requests, or IPs.
        pass

    def send_json(self,status,body):
        raw=json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path not in ("/","/health"):
            return self.send_json(404,{"error":"NOT_FOUND"})
        ready=True
        try:
            paths()
        except (OSError,ValueError,RuntimeError):
            ready=False
        self.send_json(200 if ready else 503,
                       {"service":"HAPYCH Voice Studio",
                        "tts_ready_for_private_request":ready,
                        "publishing_authorized":False,
                        "public_api":False})

    def do_POST(self):
        if self.path != "/v1/audio/speech":
            return self.send_json(404,{"error":"NOT_FOUND"})
        try:
            authorize(self.headers.get("Authorization",""))
            size=int(self.headers.get("Content-Length") or "0")
            if not 0<size<=MAX_BODY:
                raise ValueError("OWNER_TTS_REQUEST_SIZE")
            obj=json.loads(self.rfile.read(size))
            request_id=self.headers.get("X-Idempotency-Key")
            raw,reference_sha=build_audio(obj,request_id)
        except PermissionError:
            return self.send_json(403,{"error":"VOICE_AUTHORIZATION_DENIED"})
        except (ValueError,TypeError,KeyError,json.JSONDecodeError):
            return self.send_json(422,{"error":"VOICE_REQUEST_OR_QA_REJECTED"})
        except (TimeoutError,subprocess.TimeoutExpired):
            return self.send_json(503,{"error":"VOICE_COMPUTE_TIMEOUT"})
        except (RuntimeError,OSError):
            return self.send_json(503,{"error":"VOICE_SERVER_NOT_READY"})
        self.send_response(200)
        self.send_header("Content-Type","audio/wav")
        self.send_header("X-Voice-ID",VOICE_ID)
        self.send_header("X-Channel-ID",CHANNEL)
        self.send_header("X-Audio-SHA256",hashlib.sha256(raw).hexdigest())
        self.send_header("X-Reference-SHA256",reference_sha)
        self.send_header("X-TTS-Backend","qwen3_0.6b_base_owner_clone")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main():
    # Prevent accidental binding to public 0.0.0.0.
    host="127.0.0.1"
    port=int(os.environ.get("OWNER_TTS_PORT","8077"))
    ThreadingHTTPServer((host,port),Handler).serve_forever(poll_interval=0.35)


if __name__=="__main__":
    main()
