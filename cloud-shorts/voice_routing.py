"""Only owner-approved ORIGINAL voice routes: legacy DEEP and private Qwen.

No SaaS voice generations, no service usage credits, no silent fallback.
Old verified DEEP episodes remain unmodified. All future episodes choose
their speaker at creation and never change identities mid-production.
"""
from __future__ import annotations
import os
import deep_voice
import selfhosted_voice


def new_episode_configuration(environment=None):
    env = environment if environment is not None else os.environ
    provider = env.get("GUSTAVA_TTS_PROVIDER", deep_voice.VOICE_ENGINE)
    if provider == deep_voice.VOICE_ENGINE:
        return {
            "voice_engine": deep_voice.VOICE_ENGINE,
            "voice_profile": deep_voice.PROFILE_ID,
        }
    if provider == selfhosted_voice.VOICE_ENGINE:
        return {
            "voice_engine": selfhosted_voice.VOICE_ENGINE,
            "voice_profile": selfhosted_voice.PROFILE_ID,
            "selfhosted_voice_id": selfhosted_voice.VOICE_ID,
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
        return (selfhosted_voice.PROFILE_ID if
                selfhosted_voice.approved_profile(episode) else None)
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
