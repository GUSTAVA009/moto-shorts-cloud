"""Bounded motionless/oversized/unavailable footage replacement before any upload.

Never substitute an unrelated topic, reuse a previously reserved original or
commit a repair without a confirmed FAILED GitHub Actions render.
"""
from __future__ import annotations
import copy
from pathlib import Path
import re

from editorial_guard import source_id, validate_catalog
from render_episode import validate_episode
from moto_autocreate import (THEMES, pexels_results, commons_results, choose_sources)

TOPIC_HINTS = (
    (("лес", "wood", "forest"), "forest"),
    (("горы", "mountain", "склон"), "mountain"),
    (("шины", "шина", "гараж", "ремонт", "tire", "garage"), "repair"),
    (("снег", "зим", "snow"), "snow"),
    (("гонк", "мотокросс", "race"), "motocross"),
    (("город", "city", "ноч", "night"), "city"),
    (("дожд", "rain", "мокр"), "rain"),
    (("пустын", "песок", "desert"), "desert"),
)


def episode_theme(episode):
    context = (" ".join(str(episode.get(k, "")) for k in ("title", "description")) +
               " " + str((episode.get("editorial") or {}).get("environment", ""))).casefold()
    for needles, label in TOPIC_HINTS:
        if any(word in context for word in needles):
            return next(t for t in THEMES if t[0] == label)
    return None  # Never borrow a visually unrelated theme.


def discover_new_sources(theme, used_ids, pexels_key):
    found = []
    if pexels_key:
        for page in (1, 2, 3):
            found.extend(pexels_results(theme, page, pexels_key))
            if len(choose_sources(found, used_ids)) >= 2:
                break
    if len(choose_sources(found, used_ids)) < 2:
        found.extend(commons_results(theme))
    return choose_sources(found, used_ids)


def source_repair(catalog, episode_id, receipt, diagnostic, sources, permanently_used=()):
    if not receipt or receipt.get("id") != episode_id or receipt.get("state") != "reserved":
        return None
    if not 1 <= int(receipt.get("attempt_count", 0)) < 3:
        return None
    attempts = diagnostic.get("attempts") or []
    if not attempts or attempts[-1].get("status") != "technical_error":
        return None
    if attempts[-1].get("source_failure") is not True:
        return None
    episode = next((x for x in catalog["episodes"] if x["id"] == episode_id), None)
    if episode is None or episode.get("auto_publish") is not True:
        return None
    if not episode_theme(episode):
        return None
    used = set(permanently_used)
    for e in catalog["episodes"]:
        for m in e["footage"]:
            used.add(source_id(m))
    fresh = choose_sources(sources or [], used)
    if len(fresh) < 2:
        return None
    candidate = copy.deepcopy(catalog)
    updated = next(x for x in candidate["episodes"] if x["id"] == episode_id)
    updated["footage"] = [dict(x, key="repair_clip_" + str(i))
                         for i, x in enumerate(fresh)]
    updated["shots"] = [
        {"source": updated["footage"][i % len(fresh)]["key"],
         "start": round(0.20 + (i // len(fresh)) * 2.2, 2), "seconds": 2.1}
        for i in range(12)
    ]
    updated["source_revision_requested"] = True
    updated["source_revision_reason"] = "unavailable_source_replaced"
    updated["source_revision_note"] = (
        "Replaced prior blocked scene sources with newly license-verified "
        "unseen motorcycle video after confirmed technical render failure."
    )
    validate_episode(updated)
    validate_catalog(candidate)
    return candidate
