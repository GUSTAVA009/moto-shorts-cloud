"""Provider-independent checks of one original, licensed, intelligible Shorts MP4.

The quality gate belongs to GUSTAVA Enduro, not a publishing vendor.
Keep historical provider receipts only for deduplication.
"""
import hashlib
import os
import re
from pathlib import Path

from channel_focus import assert_motorcycle_episode
from visual_director import verified_visual_artifact
from deep_voice import (VOICE_ENGINE as REQUIRED_MALE_ENGINE,
                        PROFILE_ID as REQUIRED_MALE_PROFILE,
                        PUBLIC_ATTRIBUTION as DEEP_ATTRIBUTION,
                        ready as deep_audio_ready)
from cartesia_voice import (VOICE_ENGINE as CARTESIA_ENGINE,
                            PROFILE_ID as CARTESIA_PROFILE,
                            MODEL_ID as CARTESIA_MODEL,
                            supported_episode as cartesia_supported)
from selfhosted_voice import (VOICE_ENGINE as SELFHOSTED_ENGINE,
                              PROFILE_ID as SELFHOSTED_PROFILE,
                              VOICE_ID as SELFHOSTED_VOICE_ID,
                              approved_profile as selfhosted_approved_profile)


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1048576), b""):
            h.update(block)
    return h.hexdigest()



def publication_allowed(episode, meta, qa, video):
    if not episode.get("auto_publish") is True:
        raise ValueError("This episode was not explicitly queued for automatic release")
    if episode.get("visual_review_failed") is True or episode.get("visual_revision_requested") is True:
        raise ValueError("OWNER_REJECTED_VISUALS: reject unfinished or rejected visual material")
    if int(episode.get("visual_director_version") or 0) >= 3:
        if (episode.get("visual_revision_status") != "assistant_checked_passed"
                or not episode.get("scene_script_anchors")):
            raise ValueError("SCENE_FIRST_REVIEW_REQUIRED: actual shots must be reviewed for release")
    # New director-v2 releases MUST provide visual QA proof. Legacy test
    # fixtures and already-approved historic renders keep their prior proof.
    # The actual renderer and queued selector independently reject new
    # helmet videos whose source metadata shows only handlebars.
    if episode.get("visual_director_version", 0) >= 2:
        verified_visual_artifact(episode, video)
    assert_motorcycle_episode(episode)
    if meta.get("episode_id") != episode["id"] or qa.get("episode_id") != episode["id"]:
        raise ValueError("Metadata/ASR episode mismatch; do not upload")
    if episode.get("voice_engine") == REQUIRED_MALE_ENGINE:
        if not deep_audio_ready(episode):
            raise ValueError("ONLY_APPROVED_CREATE_AUDIO_DEEP: old voices or missing audio blocked")
        if (qa.get("male_voice_verified") is not True
                or qa.get("voice_profile") != REQUIRED_MALE_PROFILE
                or qa.get("voice_speaker") != "deep"
                or qa.get("voice_provider") != "aidocmaker.com"
                or qa.get("voice_source_audio_sha256") !=
                   episode["deep_audio"]["source_audio_sha256"]):
            raise ValueError("ONLY_APPROVED_CREATE_AUDIO_DEEP: genuine voice source not verified")
    elif episode.get("voice_engine") == CARTESIA_ENGINE:
        # Free Cartesia evaluations cannot be silently pushed to a
        # monetizable channel. This explicit flag is independently checked
        # by BOTH the preview-release selector and publisher.
        if os.environ.get("CARTESIA_COMMERCIAL_PLAN_CONFIRMED") != "1":
            raise ValueError("CARTESIA_COMMERCIAL_RIGHTS_NOT_VERIFIED")
        if (not cartesia_supported(episode)
                or qa.get("male_voice_verified") is not True
                or qa.get("voice_profile") != CARTESIA_PROFILE
                or qa.get("voice_speaker") != episode.get("cartesia_voice_id")
                or qa.get("voice_model_id") != CARTESIA_MODEL
                or qa.get("voice_provider") != "cartesia.ai"
                or not isinstance(qa.get("voice_source_audio_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}",
                                    qa["voice_source_audio_sha256"])):
            raise ValueError("CARTESIA_GENUINE_RUSSIAN_VOICE_SOURCE_NOT_VERIFIED")
    elif episode.get("voice_engine") == SELFHOSTED_ENGINE:
        approved_ref = os.environ.get("GUSTAVA_VOICE_REFERENCE_SHA256", "")
        if (os.environ.get("GUSTAVA_ORIGINAL_VOICE_APPROVED") != "1"
                or not re.fullmatch(r"[0-9a-f]{64}", approved_ref)):
            raise ValueError("SELFHOSTED_ORIGINAL_VOICE_NOT_APPROVED_FOR_PUBLICATION")
        if (not selfhosted_approved_profile(episode)
                or qa.get("male_voice_verified") is not True
                or qa.get("voice_profile") != SELFHOSTED_PROFILE
                or qa.get("voice_speaker") != SELFHOSTED_VOICE_ID
                or qa.get("voice_provider") != "owner_selfhosted_qwen3"
                or qa.get("selfhosted_reference_sha256") != approved_ref
                or not re.fullmatch(r"[0-9a-f]{64}",
                                    str(qa.get("voice_source_audio_sha256") or ""))):
            raise ValueError("SELFHOSTED_GENUINE_ORIGINAL_VOICE_SOURCE_NOT_VERIFIED")
    else:
        raise ValueError("UNAPPROVED_TTS_PROVIDER_FOR_PUBLICATION")
    if qa.get("passed") is not True or qa.get("status") != "passed":
        raise ValueError("Russian voice QA incomplete: no automatic release")
    if (qa.get("lexical_coverage", 0) < .97 or qa.get("ending_coverage", 0) < .95
            or qa.get("final_word_present") is not True):
        raise ValueError("Missing or clipped Russian narration")
    mix = qa.get("mixed_audio")
    if (not isinstance(mix, dict) or mix.get("episode_id") != episode["id"]
            or mix.get("source") != "FINAL_MIXED_MP4"
            or mix.get("passed") is not True or mix.get("final_word_present") is not True
            or mix.get("lexical_coverage", 0) < .97
            or mix.get("numerics_match") is not True):
        raise ValueError("Final MP4 mixed Russian narration QA failed")
    if not video.is_file() or not 100000 <= video.stat().st_size <= 150*1024*1024:
        raise ValueError("Invalid MP4 file or unexpected size")
    if video.suffix.lower() != ".mp4" or not meta.get("title") or not meta.get("description"):
        raise ValueError("Invalid upload metadata")
    if mix.get("mp4_sha256") != file_sha256(video):
        raise ValueError("Final MP4 does not match its independent mixed-audio QA proof")
    description = meta["description"]
    if len(meta["title"]) > 100:
        raise ValueError("Invalid video title")
    if episode.get("voice_engine") == REQUIRED_MALE_ENGINE:
        if DEEP_ATTRIBUTION not in description:
            raise ValueError("Missing required AI Doc Maker credit")
        safe_description = description.replace(DEEP_ATTRIBUTION, "")
    else:
        # Cartesia commercial use is not licensed by this project's old
        # AIDocMaker attribution; do not falsely credit the wrong service.
        safe_description = description
    if any(s in safe_description.lower() for s in ("https://", "www.")):
        raise ValueError("Unauthorized external links in description")
    if not episode.get("footage") or any(s.get("license") not in ("Pexels License", "CC0 1.0")
                                      for s in episode["footage"]):
        raise ValueError("Unverified commercial footage rights")
    series = episode.get("episode_series")
    if series and series.get("historical_reconstruction"):
        refs = episode.get("editorial_references") or []
        if (len(set(refs)) < 2 or any(not str(u).startswith("https://") for u in refs)
                or "иллюстративные" not in meta["description"].casefold()):
            raise ValueError("Real-event documentary lacks independent sources or illustration disclosure")
    return True


