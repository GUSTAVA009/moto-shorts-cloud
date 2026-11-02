"""Strict three-route voice transport for the approved GUSTAVA narrator.

Route 1: owner's cloud Qwen; route 2: owner Windows Qwen via HTTPS;
route 3: independently hosted Chatterbox Multilingual V3.
Never silently switch to Silero/Kokoro/V6 or an unrelated speaker.
No network calls at import time. An HTTPS endpoint alone is not proof of TTS.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from pronunciation_ru import to_speech_text

VOICE_ID = "gustava-original-v1"
CHANNEL_SLUG = "gustava"
MAX_AUDIO_BYTES = 12_000_000

# Each entry has its own revocable token; all responses must refer to the
# owner's SAME pinned reference WAV hash and same channel-scoped speaker ID.
PROVIDERS = (
    ("cloud", "GUSTAVA_SELFHOSTED_TTS_ENABLED", "GUSTAVA_VOICE",
     None, None),
    ("local_pc", "GUSTAVA_LOCAL_TTS_ENABLED", "GUSTAVA_LOCAL_VOICE",
     None, None),
    ("chatterbox_v3", "GUSTAVA_TERTIARY_TTS_ENABLED", "GUSTAVA_TERTIARY_VOICE",
     "GUSTAVA_TERTIARY_VOICE_CANARY_APPROVED", "chatterbox_multilingual_v3"),
)
TOKEN_RE = re.compile(r"gvk_[A-Za-z0-9_-]{40,64}\Z")
SHA_RE = re.compile(r"[a-f0-9]{64}\Z")
HOST_RE = re.compile(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+\Z")


@dataclass(frozen=True)
class Route:
    name: str
    url: str
    key: str
    expected_backend: str | None


class ProviderUnavailable(RuntimeError):
    """Only connectivity, timeouts and transient 429/5xx permit failover."""


def approved_endpoint(url: str, host: str) -> str:
    host = str(host or "").lower().strip()
    parsed = urllib.parse.urlsplit(str(url or ""))
    if (not HOST_RE.fullmatch(host) or parsed.scheme != "https"
            or parsed.hostname != host or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.path != "/v1/audio/speech"
            or parsed.query or parsed.fragment):
        raise ValueError("OWNER_VOICE_ENDPOINT_NOT_APPROVED")
    return str(url)


def available_routes(env=None, *, require_secret=False):
    env = os.environ if env is None else env
    if not SHA_RE.fullmatch(str(env.get("GUSTAVA_VOICE_REFERENCE_SHA256") or "")):
        return ()
    found = []
    seen = set()
    for name, enable, prefix, canary, expected_backend in PROVIDERS:
        if env.get(enable) != "1" or (canary and env.get(canary) != "1"):
            continue
        key = str(env.get(prefix + "_API_KEY") or "")
        oidc = bool(name == "cloud"
            and env.get("GUSTAVA_VOICE_OIDC_ENABLED") == "1"
            and env.get("GITHUB_REPOSITORY") == "GUSTAVA009/moto-shorts-cloud"
            and env.get("GITHUB_REF") == "refs/heads/main"
            and env.get("ACTIONS_ID_TOKEN_REQUEST_URL")
            and env.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN"))
        if require_secret:
            if not TOKEN_RE.fullmatch(key) and not oidc:
                continue
        elif (not TOKEN_RE.fullmatch(key)
              and env.get(prefix + "_KEY_PRESENT") != "true" and not oidc):
            continue
        try:
            url = approved_endpoint(env.get(prefix + "_API_URL"),
                                    env.get(prefix + "_APPROVED_HOST"))
        except (ValueError, TypeError):
            continue
        # Same URL twice is NOT independent failover.
        if url in seen:
            continue
        seen.add(url)
        found.append(Route(name, url, key, expected_backend))
    return tuple(found)


def owner_actions_oidc(env):
    """Use GitHub's ephemeral identity, rather than storing a server secret in Actions.

    The destination independently verifies the token signature, audience,
    repository_id, main branch and workflow reference before generating WAV.
    """
    if (env.get("GUSTAVA_VOICE_OIDC_ENABLED") != "1"
            or env.get("GITHUB_REPOSITORY") != "GUSTAVA009/moto-shorts-cloud"
            or env.get("GITHUB_REF") != "refs/heads/main"):
        raise RuntimeError("OWNER_GITHUB_OIDC_NOT_AUTHORIZED")
    url = str(env.get("ACTIONS_ID_TOKEN_REQUEST_URL") or "")
    token = str(env.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN") or "")
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname
            or not parsed.hostname.endswith(".actions.githubusercontent.com")
            or parsed.username or parsed.password or parsed.port not in (None,443)
            or not token or len(token) > 9000):
        raise RuntimeError("OWNER_GITHUB_OIDC_REQUEST_UNAVAILABLE")
    delim = "&" if parsed.query else "?"
    request=urllib.request.Request(
        url+delim+urllib.parse.urlencode({"audience":"voice.hapychrust.ru"}),
        headers={"Authorization":"bearer "+token,"Accept":"application/json",
                 "User-Agent":"GUSTAVA-VOICE-FACTORY"})
    with urllib.request.urlopen(request,timeout=15) as response:
        payload=json.load(__import__("io").BytesIO(response.read(10000)))
    jwt=payload.get("value")
    if not isinstance(jwt,str) or len(jwt.split("."))!=3 or len(jwt)>6500:
        raise RuntimeError("OWNER_GITHUB_OIDC_TOKEN_INVALID")
    return jwt


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _post(route: Route, episode: dict, env, *, opener=None):
    # The visual title remains «трек»; only private TTS hears «трэк».
    text = to_speech_text(episode["narration"])
    request_id = episode["id"] + "-" + hashlib.sha256(
        text.encode("utf8")).hexdigest()[:20]
    payload = {
        "text": text, "voice": VOICE_ID,
        "channel_slug": CHANNEL_SLUG, "response_format": "wav",
    }
    key = route.key
    if not TOKEN_RE.fullmatch(key) and route.name == "cloud":
        key = owner_actions_oidc(env)
    req = urllib.request.Request(
        route.url, data=json.dumps(payload, ensure_ascii=False).encode("utf8"),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "audio/wav",
            "X-Idempotency-Key": request_id,
            "User-Agent": "GUSTAVA-VOICE-FACTORY",
        }, method="POST")
    try:
        with (opener or urllib.request.build_opener(NoRedirect())).open(
                req, timeout=360) as response:
            if response.geturl() != route.url:
                raise ValueError("OWNER_VOICE_REDIRECT_BLOCKED")
            audio = response.read(MAX_AUDIO_BYTES + 1)
            headers = response.headers
    except urllib.error.HTTPError as error:
        if error.code in (408, 429, 500, 502, 503, 504):
            raise ProviderUnavailable("TTS_TRANSIENT_FAILURE_" + route.name) from None
        raise RuntimeError("TTS_REJECTED_" + route.name + "_" + str(error.code)) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        raise ProviderUnavailable("TTS_CONNECTION_UNAVAILABLE_" + route.name) from None
    reference = env["GUSTAVA_VOICE_REFERENCE_SHA256"]
    if (len(audio) > MAX_AUDIO_BYTES
            or headers.get("X-Audio-SHA256") != hashlib.sha256(audio).hexdigest()
            or headers.get("X-Reference-SHA256") != reference
            or headers.get("X-Voice-ID") != VOICE_ID
            or headers.get("X-Channel-ID") != CHANNEL_SLUG
            or (route.expected_backend is not None
                and headers.get("X-TTS-Backend") != route.expected_backend)):
        raise ValueError("OWNER_VOICE_IDENTITY_OR_AUDIO_SHA_REJECTED")
    return audio, reference, route.name


def synthesize(episode: dict, *, env=None, transport=None, validator=None):
    """Fail over ONLY on unavailable compute, not unsafe output.

    A failed generation request never counts as a WAV or finished Short.
    A returned WAV is validated by the caller's original voice QA gate.
    """
    env = os.environ if env is None else env
    routes = available_routes(env, require_secret=True)
    if not routes:
        raise RuntimeError("NO_CONFIGURED_APPROVED_TTS_PROVIDER")
    unavailable = []
    for route in routes:
        try:
            result = ((transport or _post)(route, episode, env))
            if validator is not None:
                validator(result[0])  # Bad audio is an integrity failure.
            return result
        except ProviderUnavailable:
            unavailable.append(route.name)
    raise RuntimeError("ALL_APPROVED_TTS_PROVIDERS_UNAVAILABLE:" + ",".join(unavailable))
