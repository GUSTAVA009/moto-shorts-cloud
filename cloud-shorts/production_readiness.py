"""Count *production-capable* originals, not text-only Shorts drafts.

A script with auto_preview=true and no independently approved original
voice_id=deep recording is NOT an available new MP4. This is a read-only
health helper: it never synthesizes replacement voices or silently approves
an old/rerun episode.
"""
from __future__ import annotations

from deep_voice import ready as approved_deep_ready


def inventory(catalog, reserved_ids):
    reserved = set(reserved_ids)
    waiting = [
        ep for ep in catalog.get("episodes", [])
        if ep.get("auto_preview") is True
        and ep.get("id") not in reserved
        and ep.get("editorial_rejected") is not True
        and ep.get("visual_review_failed") is not True
    ]
    with_deep = [ep for ep in waiting if approved_deep_ready(ep)]
    missing_deep = [ep for ep in waiting if not approved_deep_ready(ep)]
    rejected = [
        ep for ep in catalog.get("episodes", [])
        if ep.get("editorial_rejected") is True
        or ep.get("visual_review_failed") is True
    ]
    return {
        "unrendered_script_drafts": len(waiting),
        "unrendered_verified_deep_originals": len(with_deep),
        "unrendered_missing_original_deep": len(missing_deep),
        "rejected_visuals": len(rejected),
        "has_autonomous_deep_tts": False,
        "blockers": (["UNATTENDED_DEEP_TTS_PROVIDER_NOT_CONNECTED"]
                     if missing_deep or not with_deep else []),
    }


def production_unavailable(state):
    """Whether more fresh approved audio is needed before a renderer can run."""
    return state["unrendered_verified_deep_originals"] == 0
