"""Editorial safeguards for independent original stories across any subject.

Require unique visual sources, narrative, subjects and settings. Legacy motorcycle
catalogs use editorial.bike; all new non-motorcycle episodes use editorial.subject.
These checks cannot assess visual/factual accuracy: human review remains essential.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from urllib.parse import urlparse
from channel_focus import assert_motorcycle_episode
from moto_assets import source_id as media_source_id, validated_media

# Source footage used in the already published first YouTube video.
# Never use it again in any of the new production previews.
PUBLISHED_SOURCE_IDS = {"5803637", "5803517"}
PROFILE_FIELDS = ("environment", "people", "story", "visual")
BLOCKED_PUBLIC_TERMS = ("хапыч", "эндуро")
ID_RE = re.compile(r"-(\d{5,10})/?$")


def source_id(footage: dict) -> str:
    """Licensed video identity across Pexels and content-addressed Commons CC0."""
    return media_source_id(footage)


def editorial_subject(profile):
    """Preserve the existing motorcycle catalogue while enabling any other topic."""
    value = profile.get("subject") if "subject" in profile else profile.get("bike")
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
        raise ValueError("Invalid editorial subject (or legacy bike)")
    return value


def validate_catalog(data):
    """Fail closed before downloading any video or publishing any preview."""
    episodes = data.get("episodes")
    if not isinstance(episodes, list) or not episodes:
        raise ValueError("Episode catalog empty")
    used_source_ids = dict.fromkeys(PUBLISHED_SOURCE_IDS, "already published YouTube video")
    used_slugs = set()
    used_titles = set()
    used_narrations = set()
    used_profiles = set()
    previous = []

    for ep in episodes:
        slug = ep.get("id", "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,46}", str(slug)):
            raise ValueError("Invalid episode ID")
        if slug in used_slugs:
            raise ValueError("Episode ID already exists: " + slug)
        used_slugs.add(slug)
        if ep.get("auto_preview") is True or ep.get("auto_publish") is True:
            assert_motorcycle_episode(ep)

        for field, seen in (("title", used_titles), ("narration", used_narrations)):
            value = re.sub(r"\s+", " ", str(ep.get(field, "")).strip()).casefold()
            if not value or value in seen:
                raise ValueError("Reused or missing " + field + " in " + slug)
            seen.add(value)

        for field in ("title", "narration", "description",
                      "caption_start", "caption_middle", "caption_end"):
            text = str(ep.get(field, ""))
            if any(word in text.casefold() for word in BLOCKED_PUBLIC_TERMS):
                raise ValueError("Forbidden brand/topic in " + slug + ":" + field)

        profile = ep.get("editorial")
        if not isinstance(profile, dict):
            raise ValueError("Every episode requires an editorial scene profile")
        tag_tuple = []
        for field in PROFILE_FIELDS:
            value = profile.get(field)
            if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
                raise ValueError("Invalid editorial " + field + " in " + slug)
            tag_tuple.append(value)
        tag_tuple = tuple(tag_tuple + [editorial_subject(profile)])
        if tag_tuple in used_profiles:
            raise ValueError("Duplicate concept/profile in " + slug)
        used_profiles.add(tag_tuple)

        # For the last 3 stories, do not reuse the environment or narrative arc.
        # Motorbike and cast categories must also change from the immediately
        # previous episode. A truly new environment takes priority over editing.
        for recent in previous[-3:]:
            if profile["environment"] == recent["environment"]:
                raise ValueError("Too many near-identical settings for " + slug)
            if profile["story"] == recent["story"]:
                raise ValueError("Reused story/event arc for " + slug)
        if previous:
            if (editorial_subject(profile) == editorial_subject(previous[-1])
                    or profile["people"] == previous[-1]["people"]):
                raise ValueError("Must change both story subject and people compared with last episode")

        sources = ep.get("footage") or []
        if len(sources) < 2:
            raise ValueError("At least two distinct real-world source clips required")
        authors = set()
        for video in sources:
            video_id = source_id(video)
            validated_media(video)
            if video_id in used_source_ids:
                raise ValueError("STOCK_REUSE_FORBIDDEN: " + video_id
                                 + " was used in " + used_source_ids[video_id])
            used_source_ids[video_id] = slug
            authors.add(str(video.get("author", "")).strip().casefold())
            if video.get("license") not in ("Pexels License", "CC0 1.0"):
                raise ValueError("No verified commercial-use footage license for " + slug)
        # Existing historical episodes cannot be revised, but new episodes must
        # use two or more credited creators, not a series of shots of one actor.
        if len(previous) >= 3 and len(authors) < 2:
            raise ValueError("New episode requires at least 2 footage contributors " + slug)
        previous.append(profile)

    return {
        "episodes": len(episodes),
        "new_unique_video_clips": len(used_source_ids) - len(PUBLISHED_SOURCE_IDS),
        "unique_editorial_concepts": len(used_profiles),
    }


def validate_file(path):
    return validate_catalog(json.loads(Path(path).read_text(encoding="utf8")))


if __name__ == "__main__":
    import argparse
    a = argparse.ArgumentParser()
    a.add_argument("--catalog", type=Path, default=Path(__file__).with_name("episodes.json"))
    args = a.parse_args()
    print("EDITORIAL_UNIQUENESS_PASSED", validate_file(args.catalog))
