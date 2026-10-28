#!/usr/bin/env python3
"""Continuous, source-backed motorcycle STORY IDEA discovery — never a blind publisher.

RSS headlines are research leads, not scripts or licensed footage. New ideas
are deduplicated in GitHub's render-ledger. Editorial research and visual
rights are mandatory before promotion into episodes.json.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import preview_queue as ledger

FEEDS = [
    "https://www.rideapart.com/rss/news/all/",
    "https://thethrottlehand.com/feed.xml",
]
ALLOWED_HOSTS = {"rideapart.com", "www.rideapart.com", "thethrottlehand.com", "www.thethrottlehand.com"}
STATE_PATH = "idea-candidates/seen.json"


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
    for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        title = clean(entry.findtext("{http://www.w3.org/2005/Atom}title") or "")
        links = entry.findall("{http://www.w3.org/2005/Atom}link")
        link = next((x.get("href", "") for x in links if x.get("rel", "alternate") == "alternate"), "")
        if title and link:
            entries.append((title, link))
    return entries


def make_candidate(title, link):
    url = urllib.parse.urlsplit(link)
    if url.scheme != "https" or url.hostname not in ALLOWED_HOSTS:
        return None
    key = hashlib.sha256((url.netloc + url.path).encode("utf8")).hexdigest()[:20]
    lower = title.casefold()
    topic = ("tech" if any(w in lower for w in ("repair", "engine", "mechanic", "restore", "parts")) else
             "trip" if any(w in lower for w in ("travel", "road", "trip", "adventure", "tour")) else
             "race" if any(w in lower for w in ("race", "motogp", "rally", "rider", "dakar")) else
             "motorcycle_culture")
    return {
        "id": key, "source_headline": title,
        "source_url": urllib.parse.urlunsplit((url.scheme, url.netloc, url.path, "", "")),
        "topic": topic,
        "pitch_ru": "Исследовать, что произошло, чем это важно для мотоциклистов и какие факты можно подтвердить.",
        "status": "RESEARCH_ONLY_NOT_APPROVED_FOR_PUBLICATION",
        "verification": "Check primary sources, accuracy, chronology, context and video rights.",
        "must_create_new_script": True,
        "use_headline_as_narration": False,
        "use_source_images_without_license": False,
    }


def new_ideas(previous, entries, limit=16):
    seen = set(previous)
    candidates = []
    for title, link in entries:
        c = make_candidate(title, link)
        if c is None or c["id"] in seen:
            continue
        seen.add(c["id"])
        candidates.append(c)
        if len(candidates) >= limit:
            break
    return candidates


def get_feed(url):
    req = urllib.request.Request(url, headers={"User-Agent": "GUSTAVA-MotoResearch/1.0"})
    with urllib.request.urlopen(req, timeout=25) as res:
        body = res.read(1500000)
    return parse_rss(body)


def main():
    paths = []
    for url in FEEDS:
        try:
            paths.extend(get_feed(url))
        except (ValueError, ET.ParseError, TimeoutError, OSError) as exc:
            print("FEED_UNAVAILABLE", urllib.parse.urlsplit(url).hostname, type(exc).__name__)
    previous_entry = ledger.api(STATE_PATH)
    if previous_entry:
        import base64
        state = json.loads(base64.b64decode(previous_entry["content"]))
        if state.get("version") != 1:
            raise RuntimeError("Corrupt story history — cannot deduplicate")
    else:
        state = {"version": 1, "seen_ids": []}
    current_ids = state.get("seen_ids", [])
    if not isinstance(current_ids, list):
        raise RuntimeError("Story history format invalid")
    fresh = new_ideas(current_ids, paths)
    dest = Path("cloud-shorts/dist/story-ideas.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"source_count":len(paths), "new_count":len(fresh),
                                "candidates":fresh,
                                "disclaimer":"Not fact-checked scripts; not approved video or archival rights."},
                               ensure_ascii=False, indent=2)+"\n", encoding="utf8")
    if fresh:
        state["seen_ids"] = (current_ids + [c["id"] for c in fresh])[-10000:]
        ledger.store(STATE_PATH, state, "Record fresh motorcycle research leads",
                     old_sha=previous_entry["sha"] if previous_entry else None)
    print("NEW_ORIGINAL_RESEARCH_LEADS",len(fresh),"/",len(paths),
          "No articles or images copied to video")


if __name__ == "__main__":
    main()
