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
from production_readiness import inventory, production_unavailable
from editorial_novelty import require_novel_visual_story

TARGET_PENDING_EPISODES = 10
MAX_ADD_PER_RUN = 2

ROOT = Path(__file__).resolve().parent
CATALOG_PATH = "cloud-shorts/episodes.json"
SEEDS = ROOT / "seed_backlog.json"


def candidate(catalog, seed_bank, reserved_ids, target=2):
    """Pick a rights-cleared episode while the target has not been met."""
    if seed_bank.get("version") != 1:
        raise ValueError("Invalid curated story bank version")
    episodes = catalog["episodes"]
    pending = sum(x.get("auto_preview") is True and x["id"] not in reserved_ids
                  for x in episodes)
    if pending >= target:
        return None
    used = {x["id"] for x in episodes}
    used_media = {source_id(video) for x in episodes for video in x["footage"]}
    for scene in seed_bank["episodes"]:
        if scene["id"] in used:
            continue
        validate_episode(scene)
        require_novel_visual_story(scene, episodes)
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


def pending_originals(catalog, reserved):
    return sum(e.get("auto_preview") is True and e["id"] not in reserved
               for e in catalog["episodes"])


def prepared_active_scripts(catalog, entry):
    """Load the active 10-script batch only after its tenth Buffer sent event."""
    if not entry:
        return []
    import base64
    from rolling_batches import selected_scripts
    state = json.loads(base64.b64decode("".join(entry["content"].split()), validate=True))
    return selected_scripts(state, catalog)


def main():
    # GitHub SHA compare-and-swap protects against concurrent catalog writers.
    data = github("GET", "contents/" + CATALOG_PATH + "?ref=main")
    catalog = json.loads(base64.b64decode(data["content"]))
    tree = github("GET", "git/trees/render-ledger?recursive=1")
    if tree.get("truncated"):
        raise RuntimeError("Incomplete render receipt inventory")
    reserved = {Path(x["path"]).stem for x in tree.get("tree", [])
                if x["path"].startswith("render-receipts/")
                and x["path"].endswith(".json")}
    seeds = json.loads(SEEDS.read_text(encoding="utf8"))
    added = []
    # Never spend time/materials on unused videos if ten originals
    # are already awaiting rendering.
    if pending_originals(catalog, reserved) >= TARGET_PENDING_EPISODES:
        state = inventory(catalog, reserved)
        print("PRODUCTION_INVENTORY", json.dumps(state, ensure_ascii=False), flush=True)
        if production_unavailable(state):
            raise RuntimeError(
                "AUTONOMOUS_DEEP_TTS_MISSING: script-only backlog is not MP4 "
                "production stock; exact voice_id=deep needs independently "
                "authorized unattended provider synthesis and pinned ASR")
        print("SCRIPT_CAPACITY_HEALTHY_BUT_ONLY",
              state["unrendered_verified_deep_originals"],
              "real DEEP audio originals ready for renderer", flush=True)
        return 0

    import preview_queue as ledger
    history = ledger.decode_history(ledger.api(ledger.HISTORY_PATH))
    batch_entry = ledger.api("automation/rolling-ten.json")
    prepared = prepared_active_scripts(catalog, batch_entry)
    for index in range(MAX_ADD_PER_RUN):
        try:
            selection = candidate(catalog, seeds, reserved,
                                  target=TARGET_PENDING_EPISODES)
        except RuntimeError as exc:
            if "CURATED_STORY_BANK_EXHAUSTED" not in str(exc):
                raise
            from moto_autocreate import create_one
            try:
                selected = create_one(
                    catalog, permanently_used=set(history["used"]),
                    prepared_scripts=prepared)
            except (RuntimeError, ValueError, OSError) as failure:
                # Preserve any successfully authored stories instead of
                # losing the batch because one stock provider failed.
                if not added:
                    raise
                print("PARTIAL_STORY_BACKLOG_SOURCE_BLOCKED", type(failure).__name__,
                      str(failure)[:180], flush=True)
                break
            selection = (dict(catalog, episodes=catalog["episodes"]+[selected]),
                         selected["id"])
        if selection is None:
            break
        catalog, slug = selection
        added.append(slug)
    if not added:
        state = inventory(catalog, reserved)
        print("PRODUCTION_INVENTORY", json.dumps(state, ensure_ascii=False), flush=True)
        if production_unavailable(state):
            raise RuntimeError(
                "AUTONOMOUS_DEEP_TTS_MISSING: no new, hash-pinned DEEP audio "
                "to render; a script reserve is not an autonomous Shorts farm")
        print("NO_MORE_SCRIPTS_REQUIRED_RIGHT_NOW: verified DEEP previews",
              state["unrendered_verified_deep_originals"], flush=True)
        return 0

    content = base64.b64encode((json.dumps(catalog, ensure_ascii=False, indent=2)
                                + "\n").encode("utf8")).decode("ascii")
    github("PUT", "contents/" + CATALOG_PATH, {
        "message": "Stock rolling ten originals: " + ", ".join(added),
        "branch": "main", "sha": data["sha"], "content": content
    })
    state = inventory(catalog, reserved)
    print("NEW_STORIES_ADDED", len(added), added,
          "unrendered_backlog", pending_originals(catalog, reserved), flush=True)
    print("PRODUCTION_INVENTORY", json.dumps(state, ensure_ascii=False), flush=True)
    if production_unavailable(state):
        # Persist distinct scripts, but NEVER run a doomed renderer with no
        # genuine GUSTAVA DEEP, and never claim another Short was generated.
        raise RuntimeError(
            "NEW_SCRIPTS_AWAITING_ORIGINAL_DEEP: provider voice_id=deep "
            "has no unattended API connection; 0 new MP4 were generated")
    # GITHUB_TOKEN commits intentionally do not activate push workflows.
    # Dispatch exactly one safe renderer. Further attempts run by schedule.
    if os.getenv("GITHUB_EVENT_NAME") == "schedule":
        print("STORY_READY_FOR_NEXT_SCHEDULED_PREVIEW", added[0], flush=True)
    else:
        github("POST", "actions/workflows/daily-preview.yml/dispatches",
               {"ref": "main"})
        print("DAILY_PREVIEW_DISPATCHED", added[0], flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, urllib.error.HTTPError) as e:
        print("AUTOFILL_BLOCKED", type(e).__name__, str(e)[:240], file=sys.stderr)
        raise SystemExit(1)
