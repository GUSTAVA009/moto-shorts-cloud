"""Editorial gate for GUSTAVA Enduro: only motorcycle-related originals.

This is a safety check, not an automatic classifier of footage or factual truth.
The gate is deliberately strict: ambiguous stories stay unapproved for upload.
Archived cross-niche experiments remain in the historical catalog, but can
never be selected for rendering/publishing just by toggling auto flags.
"""
from __future__ import annotations
import re

ALLOWED_PILLARS = {None, "", "motorcycle", "moto", "enduro", "motocross", "offroad"}
# Require an actual motorcycle reference in the story, not only a generic
# hashtag or the channel name. The bike profile is independent corroboration.
MOTO_TEXT = re.compile(
    r"мото|байк|мотокросс|гонк|райдер|скутер|покатуш|шлем|эндуро|"
    r"питбайк|внедорожн|двухколёс|bmw|motorcycle|dirt.?bike|"
    r"motocross|enduro|offroad|rider",
    re.IGNORECASE,
)
MOTO_SUBJECT = re.compile(
    r"moto|motorcycle|motocross|enduro|offroad|off-road|"
    r"dirt.?bike|trail.?bike|bike|rider",
    re.IGNORECASE,
)


def is_motorcycle_episode(episode):
    if not isinstance(episode, dict):
        return False
    if episode.get("channel_fit") == "off_topic_archived":
        return False
    if episode.get("research_pillar") not in ALLOWED_PILLARS:
        return False
    profile = episode.get("editorial")
    if not isinstance(profile, dict):
        return False
    # Legacy motorcycle entries have an explicit bike type. New episodes may
    # use subject, but must declare the channel niche and a moto subject.
    bike = profile.get("bike")
    subject = profile.get("subject", "")
    niche = episode.get("channel_niche")
    if niche not in (None, "motorcycle"):
        return False
    if not (isinstance(bike, str) and bike.strip()) and not (
        niche == "motorcycle" and isinstance(subject, str)
        and MOTO_SUBJECT.search(subject)
    ):
        return False
    text = " ".join(str(episode.get(field) or "") for field in ("title", "narration"))
    return bool(MOTO_TEXT.search(text))


def assert_motorcycle_episode(episode):
    if not is_motorcycle_episode(episode):
        raise ValueError(
            "CHANNEL_TOPIC_BLOCKED: GUSTAVA Enduro accepts only original "
            "motorcycle, enduro, motocross, riding, moto-travel or bike-care stories"
        )
    return True
