"""Fail early when the owner source / approved narrator endpoint is offline.

This is an availability check, not a proof of an approved movie.
When unavailable, do NOT reserve an episode or burn its permanently unique
video-source IDs. The next scheduled Actions run can retry safely.
"""
from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request

OWNER_MEDIA_HOST = "84-252-66-87.sslip.io"


def probe_http(url, *, voice=False, opener=None):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RuntimeError("PROVIDER_PREFLIGHT_INVALID_HTTPS_URL")
    request = urllib.request.Request(
        url, headers={"User-Agent": "GUSTAVA-actions-provider-readiness/1.0"},
        method="HEAD")
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(request, timeout=7) as response:
            status = response.status
            actual = urllib.parse.urlsplit(response.geturl())
            if actual.hostname != parsed.hostname or actual.scheme != "https":
                raise RuntimeError("PROVIDER_PREFLIGHT_REDIRECT_CHANGED_HOST")
    except urllib.error.HTTPError as error:
        # FastAPI /v1/audio/speech is POST-only and may return 405 to HEAD.
        # A 401 says the voice service answered, but is NOT proof of valid OAuth.
        if voice and error.code in (401, 405):
            return
        raise RuntimeError(
            "PROVIDER_PREFLIGHT_HTTP_" + str(error.code) +
            ("_VOICE" if voice else "_ORIGINAL_FOOTAGE")) from None
    except (OSError, TimeoutError, urllib.error.URLError):
        raise RuntimeError(
            "PROVIDER_PREFLIGHT_CONNECTION_" +
            ("VOICE" if voice else "ORIGINAL_FOOTAGE")) from None
    if status not in (200, 204, 206):
        raise RuntimeError("PROVIDER_PREFLIGHT_UNEXPECTED_STATUS_" + str(status))


def require_available(episode, *, env=None, probe=probe_http):
    """Check only owner-domain exact episode media and approved TTS routes.

    A source is never replaced, marked licensed, or counted as an MP4 here.
    This routine MUST run after selecting but BEFORE GitHub dedup reservation.
    """
    env = os.environ if env is None else env
    original_urls = []
    for source in episode.get("footage") or ():
        url = str(source.get("url") or "")
        parsed = urllib.parse.urlsplit(url)
        if parsed.hostname == OWNER_MEDIA_HOST:
            if parsed.scheme != "https" or not parsed.path.startswith("/yt-factory-originals/"):
                raise RuntimeError("PROVIDER_PREFLIGHT_UNAPPROVED_OWNER_MEDIA_PATH")
            original_urls.append(url)
    for url in dict.fromkeys(original_urls):
        probe(url, voice=False)
    if episode.get("voice_engine") == "gustava_selfhosted_qwen3":
        from voice_failover import available_routes
        routes = available_routes(
            env, require_secret=False,
            voice_id=episode.get("selfhosted_voice_id"))
        if not routes:
            raise RuntimeError("PROVIDER_PREFLIGHT_NO_APPROVED_VOICE_ROUTE")
        failures = []
        for route in routes:
            try:
                probe(route.url, voice=True)
                return
            except RuntimeError as error:
                failures.append(str(error))
        raise RuntimeError("PROVIDER_PREFLIGHT_ALL_VOICE_ROUTES_DOWN:" +
                           ",".join(failures[:3]))


if __name__ == "__main__":
    raise SystemExit("This module checks a selected private episode; it never uploads.")
