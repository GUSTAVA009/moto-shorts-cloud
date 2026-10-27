#!/usr/bin/env python3
"""Authentic, non-spammy engagement requests for original motorcycle Shorts.

No bots, incentives, sub-for-sub, fake comments or 'like or else' framing.
One optional small 1.8-second CTA per episode; keep the story primary.
The same episode has ONE CTA kind, not four demands at once.
"""
from __future__ import annotations

from pathlib import Path
import re

CTA_KINDS = {"subscribe", "comment", "like", "share"}
# Very brief lower-third. 720x1280 Shorts has lower YouTube controls,
# so avoid the bottommost 190px and the rightmost 70px.
MAX_OVERLAY_CHARS = 32
FORBIDDEN = ("хапыч", "эндуро")
REQUEST_WORDS = {
    "subscribe": ("ПОДПИШ",),
    "comment": ("НАПИШ", "КОММЕНТ"),
    "like": ("ЛАЙК", "НРАВИТСЯ"),
    "share": ("ОТПРАВЬ", "ПОДЕЛИСЬ"),
}


def validate_cta(ep):
    cta = ep.get("cta")
    if not isinstance(cta, dict):
        raise ValueError("Every new Shorts episode needs a specific, optional single CTA")
    kind, overlay, sentence = (
        cta.get("kind"), cta.get("overlay"), cta.get("description")
    )
    if kind not in CTA_KINDS:
        raise ValueError("Unknown engagement CTA type")
    if not isinstance(overlay, str) or not (5 <= len(overlay.strip()) <= MAX_OVERLAY_CHARS):
        raise ValueError("CTA overlay should be short and readable")
    if not isinstance(sentence, str) or not (10 <= len(sentence.strip()) <= 150):
        raise ValueError("CTA description should be a short natural sentence")
    if not any(word in overlay.upper() for word in REQUEST_WORDS[kind]):
        raise ValueError("CTA overlay does not match its engagement type")
    for text in (overlay, sentence):
        lowered = text.casefold()
        if any(bad in lowered for bad in FORBIDDEN):
            raise ValueError("Do not use excluded brand/topic")
        if "http" in lowered or "www." in lowered or "sub4sub" in lowered:
            raise ValueError("No links or fake-engagement prompts")
        if any(term in lowered for term in ("награда за лайк", "подписка за подписку",
                                           "купи лайк", "накрут", "роботы подпишутся")):
            raise ValueError("Prohibited deceptive/incentivized engagement request")
    return cta


def build_description(ep):
    """One topic-specific request before hashtags. No Pexels/source links."""
    cta = validate_cta(ep)
    base = str(ep["description"]).strip()
    blocks = [x.strip() for x in re.split(r"\n\s*\n", base) if x.strip()]
    if not blocks:
        raise ValueError("Empty video description")
    sentence = cta["description"].strip()
    if any(sentence.casefold() in b.casefold() for b in blocks):
        return base
    last = blocks[-1]
    if last.startswith("#"):
        blocks.insert(len(blocks) - 1, sentence)
    else:
        blocks.append(sentence)
    result = "\n\n".join(blocks)
    if "http" in result.casefold() or "www." in result.casefold():
        raise ValueError("YouTube descriptions must not contain sources or links")
    return result


def overlay_filters(ep, work, total, font):
    """Reusable FFmpeg filters for a discrete end-of-Short CTA."""
    cta = validate_cta(ep)
    if total < 7.0:
        raise ValueError("CTA would dominate a sub-7-second video")
    start = max(0.1, total - 1.90)
    end = total - 0.17
    if start >= end:
        return []
    textfile = Path(work) / "engagement_lower_third.txt"
    textfile.write_text(cta["overlay"], encoding="utf8")
    # Deliberately low contrast matte and modest size; action remains visible.
    # Screen coordinates in the 720x1280 composition. Bottom 185px remain clear.
    return [
        "drawbox=x=34:y=950:w=580:h=75:color=black@0.55:t=fill:"
        "enable='between(t,%.3f,%.3f)'" % (start,end),
        "drawtext=fontfile=%s:textfile=%s:fontsize=27:fontcolor=white:"
        "borderw=1:bordercolor=black@0.9:"
        "x=(w-text_w)/2:y=972:enable='between(t,%.3f,%.3f)'"
        % (font, textfile, start, end),
    ]


def validate_cta_mix(episodes):
    """Keep audience requests varied, including comment, like and share."""
    kinds = [validate_cta(ep)["kind"] for ep in episodes]
    if len(episodes) >= 6 and len(set(kinds)) < 4:
        raise ValueError("Need at least subscribe/comment/like/share CTA variety")
    for i in range(3,len(episodes)):
        if len(set(kinds[i - 3:i + 1])) < 3:
            raise ValueError("Last four episodes repeat the same CTA too often")
    return {kind: kinds.count(kind) for kind in sorted(CTA_KINDS)}
