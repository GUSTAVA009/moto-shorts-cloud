"""Independent owner-approved speech for NEW episodes; historic Deep immutable.

New future episodes target the owner-controlled Qwen endpoint (cloud, local PC,
or approved third route) by default. Never create new Deep-only drafts that
require the assistant to generate a separate voice clip. Explicit historical
Deep records remain valid, with no silent narrator substitutions.
"""
from __future__ import annotations
import os
import deep_voice
import selfhosted_voice


def new_episode_configuration(environment=None):
    env = environment if environment is not None else os.environ
    # A blank Actions variable is NOT permission to fall back to manual Deep.
    # The OWNER selected Cartoon B as the operational narrator on 2026-11-02.
    # New episodes get B, never the older Qwen imitation/DEEP by default.
    # A draft cannot render until the SHA-attested B backend is actually online.
    provider = env.get("GUSTAVA_TTS_PROVIDER") or selfhosted_voice.VOICE_ENGINE
    if provider == deep_voice.VOICE_ENGINE:
        return {
            "voice_engine": deep_voice.VOICE_ENGINE,
            "voice_profile": deep_voice.PROFILE_ID,
        }
    if provider == selfhosted_voice.VOICE_ENGINE:
        return {
            "voice_engine": selfhosted_voice.VOICE_ENGINE,
            "voice_profile": selfhosted_voice.CARTOON_B_PROFILE_ID,
            "selfhosted_voice_id": selfhosted_voice.CARTOON_B_VOICE_ID,
        }
    raise ValueError("UNAPPROVED_TTS_PROVIDER: only original DEEP or owner Qwen")


def ready(episode, environment=None):
    engine = episode.get("voice_engine")
    if engine == deep_voice.VOICE_ENGINE:
        return deep_voice.ready(episode)
    if engine == selfhosted_voice.VOICE_ENGINE:
        return selfhosted_voice.ready(episode, environment)
    return False


def expected_profile(episode):
    if episode.get("voice_engine") == deep_voice.VOICE_ENGINE:
        return deep_voice.PROFILE_ID
    if episode.get("voice_engine") == selfhosted_voice.VOICE_ENGINE:
        return selfhosted_voice.profile_for_episode(episode)
    return None


def may_publish_with_verified_profile(episode, receipt):
    profile = expected_profile(episode)
    return bool(
        profile is not None
        and receipt.get("voice_qa_passed") is True
        and receipt.get("mixed_audio_qa_passed") is True
        and receipt.get("voice_profile") == profile
        and receipt.get("male_voice_verified") is True
    )
