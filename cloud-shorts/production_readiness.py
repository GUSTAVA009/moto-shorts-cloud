"""Read-only reality check: scripts, verified DEEP and preflighted Cartesia are different.

A Cartesia candidate with configured API secret/voice is NOT a ready WAV or
MP4. Only its eventual SHA-pinned audio and independent Russian ASR can admit
the rendered preview to QA. No fallback to disallowed voices.
"""
from __future__ import annotations

from deep_voice import ready as approved_deep_ready, VOICE_ENGINE as DEEP_ENGINE
from cartesia_voice import ready as cartesia_preflight, VOICE_ENGINE as CARTESIA_ENGINE
from selfhosted_voice import ready as selfhosted_preflight, VOICE_ENGINE as SELFHOSTED_ENGINE


def inventory(catalog, reserved_ids):
    reserved = set(reserved_ids)
    waiting = [
        ep for ep in catalog.get("episodes", [])
        if ep.get("auto_preview") is True
        and ep.get("id") not in reserved
        and ep.get("editorial_rejected") is not True
        and ep.get("visual_review_failed") is not True
    ]
    deep_episodes = [ep for ep in waiting
                     if ep.get("voice_engine") == DEEP_ENGINE]
    new_deep = [ep for ep in deep_episodes if approved_deep_ready(ep)]
    missing_deep = [ep for ep in deep_episodes if not approved_deep_ready(ep)]
    cartesia_episodes = [ep for ep in waiting
                         if ep.get("voice_engine") == CARTESIA_ENGINE]
    cartesia_available = [ep for ep in cartesia_episodes
                          if cartesia_preflight(ep)]
    missing_cartesia = len(cartesia_episodes) - len(cartesia_available)
    selfhosted_episodes = [ep for ep in waiting
                           if ep.get("voice_engine") == SELFHOSTED_ENGINE]
    selfhosted_available = [ep for ep in selfhosted_episodes
                            if selfhosted_preflight(ep)]
    missing_selfhosted = len(selfhosted_episodes) - len(selfhosted_available)
    rejected = [
        ep for ep in catalog.get("episodes", [])
        if ep.get("editorial_rejected") is True
        or ep.get("visual_review_failed") is True
    ]
    blockers = []
    if missing_deep:
        blockers.append("UNATTENDED_DEEP_TTS_PROVIDER_NOT_CONNECTED")
    if missing_cartesia:
        blockers.append("CARTESIA_KEY_VOICE_OR_ACTIVATION_MISSING")
    if missing_selfhosted:
        blockers.append("SELFHOSTED_GPU_API_KEY_OR_VOICE_REFERENCE_NOT_CONNECTED")
    return {
        "unrendered_script_drafts": len(waiting),
        "unrendered_verified_deep_originals": len(new_deep),
        "unrendered_missing_original_deep": len(missing_deep),
        "unrendered_cartesia_api_candidates": len(cartesia_available),
        "unrendered_cartesia_not_configured": missing_cartesia,
        "unrendered_selfhosted_api_candidates": len(selfhosted_available),
        "unrendered_selfhosted_not_configured": missing_selfhosted,
        "rejected_visuals": len(rejected),
        "has_autonomous_deep_tts": False,
        "has_cartesia_api_configured": bool(cartesia_available),
        "blockers": blockers,
    }


def production_unavailable(state):
    """Existing original DEEP assets or *preflighted* Cartesia can start render.

    A Cartesia preview is NOT a finished MP4 before TTS, ASR and video QA.
    """
    return (state["unrendered_verified_deep_originals"] == 0 and
            state.get("unrendered_cartesia_api_candidates", 0) == 0 and
            state.get("unrendered_selfhosted_api_candidates", 0) == 0)
