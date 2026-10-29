#!/usr/bin/env python3
"""Replenish GUSTAVA Enduro with ONE pre-researched, rights-recorded original.

GitHub Actions' GITHUB_TOKEN commits do not trigger push workflows. After a
successful compare-and-swap commit, explicitly dispatch daily-preview.yml.
This finite curated seed bank is not presented as an unlimited AI generator.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

from editorial_guard import validate_catalog, source_id
from render_episode import validate_episode

ROOT = Path(__file__).resolve().parent
CATALOG_PATH = "cloud-shorts/episodes.json"
SEEDS = ROOT / "seed_backlog.json"


def candidate(catalog, seed_bank, reserved_ids):
    """Pick only if fewer than two ready-to-render, genuinely new stories remain."""
    if seed_bank.get("version") != 1:
        raise ValueError("Invalid curated story bank version")
    episodes = catalog["episodes"]
    pending = sum(x.get("auto_preview") is True and x["id"] not in reserved_ids
                  for x in episodes)
    if pending >= 2:
        return None
    used = {x["id"] for x in episodes}
    used_media = {source_id(video) for x in episodes for video in x["footage"]}
    for scene in seed_bank["episodes"]:
        if scene["id"] in used:
            continue
        validate_episode(scene)
        if any(source_id(media) in used_media for media in scene["footage"]):
            raise ValueError("Seed footage already used; manual research needed")
        new_catalog = dict(catalog, episodes=episodes + [scene])
        validate_catalog(new_catalog)
        return new_catalog, scene["id"]
    if pending == 0:
        raise RuntimeError("CURATED_STORY_BANK_EXHAUSTED: new independently sourced footage needed")
    return None


def github(method, path, payload=None):
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or repo != "GUSTAVA009/moto-shorts-cloud":
        raise RuntimeError("Actions token or repository scope unavailable")
    endpoint = "https://api.github.com/repos/" + repo + "/" + path
    data = json.dumps(payload).encode("utf8") if payload is not None else None
    req = urllib.request.Request(endpoint, data=data, method=method, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "gustava-editorial-autofill",
    })
    with urllib.request.urlopen(req, timeout=35) as res:
        raw = res.read(8_000_000)
        return json.loads(raw) if raw else {}


def main():
    # Race-safe inventory fetched only at the start of this single-worker job.
    data = github("GET", "contents/" + CATALOG_PATH + "?ref=main")
    catalog = json.loads(base64.b64decode(data["content"]))
    tree = github("GET", "git/trees/render-ledger?recursive=1")
    if tree.get("truncated"):
        raise RuntimeError("Incomplete render receipt inventory")
    reserved = {Path(x["path"]).stem for x in tree.get("tree", [])
                if x["path"].startswith("render-receipts/")
                and x["path"].endswith(".json")}
    seeds = json.loads(SEEDS.read_text(encoding="utf8"))
    selection = candidate(catalog, seeds, reserved)
    if selection is None:
        print("BACKLOG_HEALTHY: queued originals still available")
        return 0
    catalog, slug = selection
    content = base64.b64encode((json.dumps(catalog, ensure_ascii=False, indent=2)
                                + "\n").encode("utf8")).decode("ascii")
    # A version mismatch yields HTTP 409; never overwrite a competing writer.
    github("PUT", "contents/" + CATALOG_PATH, {
        "message": "Schedule next verified original motorcycle Short " + slug,
        "branch": "main",
        "sha": data["sha"],
        "content": content,
    })
    print("NEW_STORY_ADDED", slug, flush=True)
    # GitHub blocks GITHUB_TOKEN-created push triggers. A scheduled refill
    # already precedes the regular renderer by 10 minutes, so don't dispatch
    # a second identical render run. Manual/push refills may dispatch once.
    if os.getenv("GITHUB_EVENT_NAME") == "schedule":
        print("STORY_READY_FOR_NEXT_SCHEDULED_PREVIEW", slug, flush=True)
    else:
        github("POST", "actions/workflows/daily-preview.yml/dispatches",
               {"ref": "main"})
        print("DAILY_PREVIEW_DISPATCHED", slug, flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, urllib.error.HTTPError) as e:
        print("AUTOFILL_BLOCKED", type(e).__name__, str(e)[:240], file=sys.stderr)
        raise SystemExit(1)
