"""Provider-safe voice selection for the GUSTAVA Shorts pipeline.

Legacy DEEP audio is still required to carry its exact frozen original MP3.
New Cartesia Sonic 3.6 episodes can request one authorized paid API call
only when secret/voice/production gate and monthly budget are configured.
No silent voice fallback or automatic publication eligibility.
"""
from __future__ import annotations
import os

import cartesia_voice
import deep_voice


def new_episode_configuration(environment=None):
    env = environment if environment is not None else os.environ
    provider = env.get("GUSTAVA_TTS_PROVIDER", deep_voice.VOICE_ENGINE)
    if provider == deep_voice.VOICE_ENGINE:
        return {
            "voice_engine": deep_voice.VOICE_ENGINE,
            "voice_profile": deep_voice.PROFILE_ID,
        }
    if provider == cartesia_voice.VOICE_ENGINE:
        pinned = cartesia_voice.parse_voice_id(
            env.get("CARTESIA_VOICE_ID", ""))
        return {
            "voice_engine": cartesia_voice.VOICE_ENGINE,
            "voice_profile": cartesia_voice.PROFILE_ID,
            "cartesia_voice_id": pinned,
        }
    raise ValueError("UNAPPROVED_TTS_PROVIDER: no replacement speaker permitted")


def ready(episode, environment=None):
    engine = episode.get("voice_engine")
    if engine == deep_voice.VOICE_ENGINE:
        return deep_voice.ready(episode)
    if engine == cartesia_voice.VOICE_ENGINE:
        return cartesia_voice.ready(episode, environment)
    return False


def expected_profile(episode):
    if episode.get("voice_engine") == deep_voice.VOICE_ENGINE:
        return deep_voice.PROFILE_ID
    if episode.get("voice_engine") == cartesia_voice.VOICE_ENGINE:
        return (cartesia_voice.PROFILE_ID if
                cartesia_voice.supported_episode(episode) else None)
    return None


def may_publish_with_verified_profile(episode, receipt):
    """Preserve exact matching voice identity across release receipts."""
    profile = expected_profile(episode)
    return bool(profile is not None
                and receipt.get("voice_qa_passed") is True
                and receipt.get("mixed_audio_qa_passed") is True
                and receipt.get("voice_profile") == profile
                and receipt.get("male_voice_verified") is True)
