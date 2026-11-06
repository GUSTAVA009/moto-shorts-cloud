#!/usr/bin/env python3
"""Select one approved original MP4 for direct YouTube; no provider call to post."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import preview_queue as ledger
from find_pending_publication import gh, select
from find_pending_buffer import complete_artifact_inventory

REPO = "GUSTAVA009/moto-shorts-cloud"


def selected_or_none(catalog, receipts, artifacts, render_paths, direct_paths):
    legacy = {Path(p).stem for p in render_paths
              if p.endswith(".json") and (
                  p.startswith("publication-receipts/")
                  or p.startswith("buffer-publication-receipts/"))}
    direct = {Path(p).stem for p in direct_paths
              if p.startswith("upload-receipts/by-episode/") and p.endswith(".json")}
    # Any YouTube upload reservation, even if incomplete, blocks another send.
    return select(catalog, receipts, legacy | direct, artifacts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if __import__("os").environ.get("GITHUB_REPOSITORY") != REPO:
        raise RuntimeError("WRONG_REPOSITORY_DIRECT_YOUTUBE")
    render = gh("git/trees/render-ledger?recursive=1")
    uploads = gh("git/trees/upload-ledger?recursive=1")
    if render.get("truncated") or uploads.get("truncated"):
        raise RuntimeError("INCOMPLETE_PUBLICATION_LEDGER")
    render_paths = [x["path"] for x in render.get("tree", []) if x.get("type") == "blob"]
    direct_paths = [x["path"] for x in uploads.get("tree", []) if x.get("type") == "blob"]
    receipts = []
    for path in render_paths:
        if not path.startswith("render-receipts/") or not path.endswith(".json"):
            continue
        entry = ledger.api(path)
        if not entry:
            raise RuntimeError("MISSING_RENDER_RECEIPT")
        receipts.append(ledger.decode_receipt(entry))
    catalog = json.loads(Path(__file__).with_name("episodes.json").read_text(encoding="utf8"))
    artifacts = complete_artifact_inventory()
    found = selected_or_none(catalog, receipts, artifacts, render_paths, direct_paths)
    if found:
        run, episode, artifact = found
        args.output.write_text("has_job=true\nepisode=" + episode +
                               "\nrender_id=" + str(run) + "\nartifact_name=" +
                               artifact + "\n", encoding="utf8")
        print("DIRECT_YOUTUBE_RELEASE_CANDIDATE", episode, run)
    else:
        args.output.write_text("has_job=false\n", encoding="utf8")
        print("NO_APPROVED_UNPUBLISHED_QA_MP4_FOR_DIRECT_YOUTUBE")


if __name__ == "__main__":
    main()
