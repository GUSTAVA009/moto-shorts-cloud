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
MAX_ENTRIES = 2000


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
        raw = response.read(12_000_001)
    if len(raw) > 12_000_000:
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
    """Use every owned, unpublished original once, even across render batches.

    Preserve the preference for TWO shots from one production batch, but
    remove the unnecessary rule that two independently owned action clips
    must share a batch timestamp. It stranded good shots after one failure.
    Actual MP4 SHA, provenance, different visible actions and independent
    final-video frame review still apply. No duplicate footage in one short.
    """
    used = set(used)
    available = [item for item in verified_feed()
                 if source_id(item) not in used]
    available.sort(key=lambda item: (
        item.get("generation_batch", ""), item.get("scene_action", ""),
        item["original_sha256"]))
    grouped = {}
    for item in available:
        grouped.setdefault(item["generation_batch"], []).append(item)
    pairs = []
    committed = set()

    def compatible(first, second):
        return (source_id(first) != source_id(second)
                and first["scene_action"] != second["scene_action"]
                and (not theme
                     or any(theme in ACTION_TOPICS[i["scene_action"]]
                            for i in (first, second))))
    # First preserve intentionally matched, distinct-action filming prompts.
    for batch, clips in sorted(grouped.items()):
        for first in clips:
            if source_id(first) in committed:
                continue
            second = next((item for item in clips
                           if source_id(item) not in committed
                           and compatible(first, item)), None)
            if second is not None:
                pairs.append([first, second])
                committed.update((source_id(first), source_id(second)))
    # Remaining owned shots can be assembled as independent contrasting
    # scenes. Their narration explicitly describes two unrelated videos.
    pending = [item for item in available if source_id(item) not in committed]
    for index, first in enumerate(pending):
        if source_id(first) in committed:
            continue
        second = next((other for other in pending[index + 1:]
                       if source_id(other) not in committed
                       and compatible(first, other)), None)
        if second is not None:
            pairs.append([first, second])
            committed.update((source_id(first), source_id(second)))
    return pairs


def original_results(theme,used_ids=()):
    """Supply both clips in their batch, not a lone action with a fake peer."""
    kind=theme[0] if isinstance(theme,(tuple,list)) else str(theme)
    return [item for pair in action_pairs(used_ids,kind) for item in pair]


def all_original_results(used_ids=()):
    return [item for pair in action_pairs(used_ids) for item in pair]
