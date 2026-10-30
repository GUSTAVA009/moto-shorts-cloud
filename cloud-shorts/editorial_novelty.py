"""Conservative visual-story novelty gate for licensed motorcycle footage.

Video IDs, URLs, random suffixes, and regenerated captions do NOT make an
identical scenic travel montage editorially new. Use only provider source
titles, not self-authored topic tags or fabricated scene-profile values.

This is a fail-closed *preflight*, not a substitute for actual frame review,
visual embedding comparisons, or proof that a narrated action occurs on film.
"""
from __future__ import annotations
import re

SCENIC = re.compile(
    r"\b(scenic|mountain|mountains|highland|ladakh|forest|forested|"
    r"autumn|landscape|sunset|countryside|road\s*trip|roadtrip|"
    r"touring|trail|hills|serene|nature|valley|rural)\b",
    re.IGNORECASE,
)
PROVIDER_ACTION = re.compile(
    r"\b(repair|restor|mechanic|adjust|assemble|inspection|"
    r"race|racing|motocross|jump|stunt|training|rescu|"
    r"loading|workshop|tire|wheel|engine|brake|service)\b",
    re.IGNORECASE,
)


def provider_titles(episode):
    """Use producer descriptions, not editable 'topics' and scene tags."""
    return [
        " ".join((str(source.get("source_title") or ""),
                  str(source.get("source_page") or ""))).lower()
        for source in episode.get("footage") or []
    ]


def is_scenic_only_montage(episode):
    titles = provider_titles(episode)
    if len(titles) < 2:
        return False
    scenic = sum(bool(SCENIC.search(title)) for title in titles)
    actions = sum(bool(PROVIDER_ACTION.search(title)) for title in titles)
    return scenic >= 2 and actions == 0


def is_repeated_visual_formula(candidate, previous_episodes):
    if not is_scenic_only_montage(candidate):
        return False
    previously = [
        ep for ep in previous_episodes
        if ep.get("id") != candidate.get("id")
        and is_scenic_only_montage(ep)
    ]
    return len(previously) >= 2


def require_novel_visual_story(candidate, previous_episodes):
    """Block more generic mountain/forest scenery, even with new video IDs."""
    if candidate.get("editorial_rejected") is True:
        raise ValueError("OWNER_REJECTED_VISUAL_STORY")
    if is_repeated_visual_formula(candidate, previous_episodes):
        raise ValueError(
            "REPEATED_SCENIC_MONTAGE: fresh video URLs, route names and "
            "captions are not a new event. Find source footage of a distinct "
            "verifiable real action or story before generating another Short."
        )
