"""Read-only intake for ORIGINAL user-owned LTX videos, never stock scraping.

The owner-controlled HTTPS server serves only new outputs that the separately
installed idle-GPU LTX producer wrote through an SSH-authenticated file path.
An asset is a SOURCE CANDIDATE, never proof that its claimed action occurred.
The final MP4 must still pass actual six-frame independent vision review,
original Cartoon B voice SHA, narration ASR, rights and per-video dedup.
"""
from __future__ import annotations

from functools import lru_cache
import json
import os
import urllib.request

from moto_assets import validated_media, source_id, ORIGINAL_FEED_URL

ACTION_TOPICS = {
    "riding": ("training", "roadtrip", "motocross"),
    "jump": ("motocross", "racing", "training"),
    "repair": ("repair", "vintage"),
    "helmet": ("helmet", "training"),
    "mud": ("dirt", "motocross"),
    "city": ("city", "rain"),
    "forest": ("forest", "roadtrip"),
    "mountain": ("mountain", "roadtrip"),
    "wheel": ("repair", "vintage"),
    "rain": ("rain", "city"),
}
MAX_ENTRIES = 400


@lru_cache(maxsize=1)
def verified_feed():
    """One fixed, low-rate owner's own manifest per GitHub worker process."""
    configured = os.getenv("GUSTAVA_ORIGINAL_FEED_URL", "").strip()
    if not configured:
        return []
    if configured != ORIGINAL_FEED_URL:
        raise ValueError("ORIGINAL_FEED_NOT_OWNER_CONTROLLED")
    request = urllib.request.Request(
        configured,
        headers={"User-Agent":"GUSTAVA-Factory-Original-Intake/1.0",
                 "Accept":"application/json"},
    )
    with urllib.request.urlopen(request, timeout=18) as response:
        if response.geturl() != configured:
            raise ValueError("ORIGINAL_FEED_REDIRECT_FORBIDDEN")
        raw = response.read(3_000_001)
    if len(raw) > 3_000_000:
        raise ValueError("ORIGINAL_FEED_OVERSIZED")
    data = json.loads(raw)
    if (not isinstance(data,dict) or data.get("version") != 1
            or data.get("provider") != "gustava-ltx-original"
            or not isinstance(data.get("sources"),list)
            or len(data["sources"]) > MAX_ENTRIES):
        raise ValueError("ORIGINAL_FEED_UNTRUSTED_MANIFEST")
    accepted = []
    seen = set()
    for item in data["sources"]:
        if not isinstance(item,dict):
            raise ValueError("ORIGINAL_FEED_INVALID_ENTRY")
        # Public manifest entries must keep the immutable producer key.
        # Only AFTER a valid source is moved into a storyboard may its
        # internal key become clip_0 or clip_1.
        if item.get("key") != "gustava_original_" + str(item.get("original_sha256") or "")[:16]:
            raise ValueError("ORIGINAL_FEED_PRODUCER_KEY_CHANGED")
        key = source_id(item)
        if key in seen:
            raise ValueError("ORIGINAL_FEED_REPEATED_SHA")
        seen.add(key)
        validated_media(item)
        if item.get("scene_action") not in ACTION_TOPICS:
            raise ValueError("ORIGINAL_FEED_UNRECOGNIZED_ACTION")
        accepted.append(item)
    return accepted


def action_pairs(used=(), theme=None):
    """No fake two-creator stock attribution; require two original videos
    of DISTINCT actions belonging to SAME signed-production batch."""
    used = set(used)
    batches = {}
    for item in verified_feed():
        if source_id(item) in used:
            continue
        if theme and theme not in ACTION_TOPICS[item["scene_action"]]:
            continue
        batches.setdefault(item["generation_batch"],[]).append(item)
    pairs=[]
    for name, entries in batches.items():
        if len(entries)!=2 or entries[0]["scene_action"]==entries[1]["scene_action"]:
            continue
        pair=sorted(entries,key=lambda a:a["scene_action"])
        pairs.append((name,pair))
    pairs.sort(key=lambda e:e[0])
    return [pair for _,pair in pairs]


def original_results(theme,used_ids=()):
    """Supply both clips in their batch, not a lone action with a fake peer."""
    kind=theme[0] if isinstance(theme,(tuple,list)) else str(theme)
    return [item for pair in action_pairs(used_ids,kind) for item in pair]


def all_original_results(used_ids=()):
    return [item for pair in action_pairs(used_ids) for item in pair]
