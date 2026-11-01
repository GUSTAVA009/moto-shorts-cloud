"""Persistent, append-only cache of independently licensed Commons CC0 videos.

One Commons query per worker cycle is already enforced by moto_autocreate.
This module retains the approved metadata across cycles on the existing
render-ledger branch, so one result is not thrown away just because no
complete two-scene script can yet be assembled. Candidate != reviewed MP4.

No raw videos, secrets, YouTube content or non-CC0 material are stored.
An actual render still rechecks the live Commons license and file SHA-1.
"""
from __future__ import annotations

import base64
import json
import urllib.error

from moto_assets import source_id, validated_media

LEDGER_PATH = "automation/cc0-source-pool.json"
LEDGER_REF = "render-ledger"
MAX_SOURCES = 300


def decode(entry):
    """Strictly read immutable source identities from GitHub's content API."""
    if entry is None:
        return {"version": 1, "sources": []}
    if not isinstance(entry, dict) or not isinstance(entry.get("content"), str):
        raise RuntimeError("CC0_SOURCE_LEDGER_MALFORMED")
    raw = base64.b64decode("".join(entry["content"].split()), validate=True)
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("version") != 1:
        raise RuntimeError("CC0_SOURCE_LEDGER_VERSION_UNSUPPORTED")
    if not isinstance(data.get("sources"), list):
        raise RuntimeError("CC0_SOURCE_LEDGER_SOURCES_INVALID")
    if len(data["sources"]) > MAX_SOURCES:
        raise RuntimeError("CC0_SOURCE_LEDGER_TOO_LARGE")
    ids = set()
    for item in data["sources"]:
        if not isinstance(item, dict) or item.get("license") != "CC0 1.0":
            raise RuntimeError("CC0_SOURCE_LEDGER_LICENSE_UNVERIFIED")
        validated_media(item)
        identity = source_id(item)
        if identity in ids:
            raise RuntimeError("CC0_SOURCE_LEDGER_DUPLICATE_ID")
        ids.add(identity)
    return data


def append_new(data, candidates):
    """Add only genuinely new CC0 identities; never overwrite prior proof."""
    if not isinstance(candidates, list):
        raise ValueError("CC0_SOURCE_DISCOVERY_INVALID_RESPONSE")
    existing = {source_id(x) for x in data["sources"]}
    merged = list(data["sources"])
    added = 0
    for item in candidates:
        if not isinstance(item, dict) or item.get("license") != "CC0 1.0":
            raise ValueError("CC0_SOURCE_NOT_CONFIRMED")
        validated_media(item)
        sid = source_id(item)
        if sid in existing:
            continue
        if len(merged) >= MAX_SOURCES:
            break
        # The trusted Commons API metadata and SHA-1 are part of the record;
        # preserving them lets renderer independently re-validate on download.
        merged.append(item)
        existing.add(sid)
        added += 1
    return {"version": 1, "sources": merged}, added


def discover(theme, github_client=None, commons_search=None):
    """One authorized official Commons query plus persistent GitHub CAS cache.

    A rate-limit or broken source *never* clears the last good stock cache.
    The worker propagates the failure and defers until its next cron cycle.
    """
    if github_client is None:
        from autofill_catalog import github as github_client
    if commons_search is None:
        from moto_autocreate import commons_results as commons_search

    old = None
    try:
        old = github_client("GET", "contents/" + LEDGER_PATH +
                            "?ref=" + LEDGER_REF)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    data = decode(old)
    # This is bounded by the outer create_one code to one search/cycle.
    fresh = commons_search(theme)
    merged, added = append_new(data, fresh)
    if added:
        payload = {
            "message": "Accumulate " + str(added) +
                       " new Commons CC0 verified video candidates",
            "branch": LEDGER_REF,
            "content": base64.b64encode(
                (json.dumps(merged, ensure_ascii=False, indent=2) +
                 "\n").encode("utf8")).decode("ascii"),
        }
        if old is not None:
            if not old.get("sha"):
                raise RuntimeError("CC0_SOURCE_LEDGER_SHA_MISSING")
            payload["sha"] = old["sha"]
        github_client("PUT", "contents/" + LEDGER_PATH, payload)
    print("CC0_SOURCE_CANDIDATES_STORED",
          json.dumps({"added": added, "cached": len(merged["sources"]),
                      "real_mp4": 0}, ensure_ascii=False), flush=True)
    return merged["sources"]
