#!/usr/bin/env python3
"""Motorcycle-specific RESEARCH leads; not an automatic article-to-video scraper.

Headlines/links are for internal verification. Never republish the headline,
website images, video, article or original narration without permission.
A new item is a research candidate ONLY, not permission to create/publish MP4.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import preview_queue as ledger

# Each feed is a research signal, NOT a source of commercially licensed video.
# Using several publishers reduces dependence on a single motorcycle niche.
FEEDS = [
    ("https://www.rideapart.com/rss/news/all/", "motorcycle"),
    ("https://thethrottlehand.com/feed.xml", "motorcycle"),
]
# Other archived research helpers remain for historical experiments, but the
# scheduled collector never gathers non-motorcycle ideas for GUSTAVA Enduro.

ALLOWED_HOSTS = {
    "rideapart.com", "www.rideapart.com",
    "thethrottlehand.com", "www.thethrottlehand.com",
    "sciencedaily.com", "www.sciencedaily.com",
    "jpl.nasa.gov", "www.jpl.nasa.gov",
    "cneos.jpl.nasa.gov",
}
RESEARCH_PILLARS = frozenset({
    "motorcycle", "science", "engineering", "nature", "history",
    "surprising_facts", "space",
})
STATE_PATH = "idea-candidates/seen.json"
# A broad entertainment channel should not generate sensitive medical,
# political or sensationalized tragedy clips from a single unverified headline.
HIGH_STAKES = re.compile(
    r"\b(cancer|stroke|alzheimers|alzheimer|suicide|murder|killed|terror|"
    r"warfare|election|president|vaccine|dementia|clinical trial|"
    r"diabetes|heart disease|covid|children dying|fatal crash)\b",
    flags=re.IGNORECASE,
)


def clean(value):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", "", str(value))).strip()[:220]


def parse_rss(xml):
    root = ET.fromstring(xml)
    entries = []
    for item in root.findall(".//item"):
        title = clean(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        if title and link:
            entries.append((title, link))
    atom = "{http://www.w3.org/2005/Atom}"
    for entry in root.findall(".//" + atom + "entry"):
        title = clean(entry.findtext(atom + "title") or "")
        links = entry.findall(atom + "link")
        link = next((x.get("href", "") for x in links
                     if x.get("rel", "alternate") == "alternate"), "")
        if title and link:
            entries.append((title, link))
    return entries


def make_candidate(title, link, pillar=None):
    url = urllib.parse.urlsplit(link)
    if url.scheme != "https" or url.hostname not in ALLOWED_HOSTS:
        return None
    if HIGH_STAKES.search(title):
        return None
    if pillar is not None and pillar not in RESEARCH_PILLARS:
        return None
    key = hashlib.sha256(
        (url.netloc.casefold() + url.path.rstrip("/")).encode("utf8")
    ).hexdigest()[:20]
    lower = title.casefold()
    legacy_topic = (
        "tech" if any(w in lower for w in ("repair", "engine", "mechanic", "restore", "parts"))
        else "trip" if any(w in lower for w in ("travel", "road", "trip", "adventure", "tour"))
        else "race" if any(w in lower for w in ("race", "motogp", "rally", "rider", "dakar"))
        else "motorcycle_culture"
    )
    topic = pillar or legacy_topic
    return {
        "id": key, "source_headline": clean(title),
        "source_url": urllib.parse.urlunsplit((url.scheme, url.netloc, url.path, "", "")),
        "topic": topic, "pillar": pillar or "motorcycle",
        "pitch_ru": "Исследовать один необычный факт; найти первоисточник, контекст, объяснение и неожиданную, но правдивую развязку.",
        "status": "RESEARCH_ONLY_NOT_APPROVED_FOR_PUBLICATION",
        "verification": "Two independent corroborating sources, correct context, exact date, original script, commercial footage rights and final Russian speech QA.",
        "sources_required": 2,
        "must_create_new_script": True,
        "use_headline_as_narration": False,
        "use_source_images_without_license": False,
        "auto_publish": False,
    }


def new_ideas(previous, entries, limit=24, per_pillar=5):
    """Fair, deduplicated lead picking across different research pillars."""
    seen = set(previous)
    count = Counter()
    candidates = []
    for row in entries:
        if not isinstance(row, (tuple, list)) or len(row) not in (2, 3):
            continue
        title, link = row[:2]
        pillar = row[2] if len(row) == 3 else None
        c = make_candidate(title, link, pillar)
        if c is None or c["id"] in seen or count[c["pillar"]] >= per_pillar:
            continue
        seen.add(c["id"])
        count[c["pillar"]] += 1
        candidates.append(c)
        if len(candidates) >= limit:
            break
    return candidates


def get_feed(url):
    req = urllib.request.Request(url, headers={"User-Agent": "GUSTAVA-Research/2.0"})
    with urllib.request.urlopen(req, timeout=25) as res:
        body = res.read(1500000)
    return parse_rss(body)


def round_robin_groups(groups):
    """Avoid bias where the first RSS source uses the entire daily quota."""
    max_len = max((len(rows) for _, rows in groups), default=0)
    for index in range(max_len):
        for pillar, rows in groups:
            if index < len(rows):
                title, link = rows[index]
                yield (title, link, pillar)


def main():
    groups = []
    for url, pillar in FEEDS:
        try:
            groups.append((pillar, get_feed(url)))
        except (ValueError, ET.ParseError, TimeoutError, OSError) as exc:
            print("FEED_UNAVAILABLE", urllib.parse.urlsplit(url).hostname,
                  pillar, type(exc).__name__)
    entries = list(round_robin_groups(groups))
    previous_entry = ledger.api(STATE_PATH)
    if previous_entry:
        import base64
        state = json.loads(base64.b64decode(previous_entry["content"]))
        if state.get("version") != 1:
            raise RuntimeError("Corrupt research history: cannot deduplicate")
    else:
        state = {"version": 1, "seen_ids": []}
    current_ids = state.get("seen_ids", [])
    if not isinstance(current_ids, list):
        raise RuntimeError("Research history format invalid")
    fresh = new_ideas(current_ids, entries)
    by_pillar = dict(Counter(c["pillar"] for c in fresh))
    dest = Path("cloud-shorts/dist/story-ideas.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps({
            "source_count": len(entries), "new_count": len(fresh),
            "by_pillar": by_pillar, "candidates": fresh,
            "disclaimer": "Research only. No source article, photography or video is licensed for republication. No auto-generation without fact checking.",
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf8",
    )
    if fresh:
        state["seen_ids"] = (current_ids + [c["id"] for c in fresh])[-10000:]
        ledger.store(STATE_PATH, state, "Persist deduplicated general-interest research leads",
                     old_sha=previous_entry["sha"] if previous_entry else None)
    print("NEW_ORIGINAL_RESEARCH_LEADS", len(fresh), "/",
          len(entries), "PILLARS", by_pillar, "NO_AUTO_PUBLISH")


if __name__ == "__main__":
    main()
