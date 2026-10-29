#!/usr/bin/env python3
"""Select a unique, independently QA-passed Shorts artifact for Buffer.

Both historical publication receipts and Buffer reservations exclude repeats.
No upload or public action occurs in the selector.
"""
import argparse
import base64
import json
import os
from pathlib import Path

import preview_queue as ledger
from find_pending_publication import gh, select


def select_for_buffer(catalog, receipts, artifact_list, tree_paths):
    dispatched = {Path(p).stem for p in tree_paths if
                  (p.startswith("publication-receipts/") or
                   p.startswith("buffer-publication-receipts/"))
                  and p.endswith(".json")}
    # Each active reservation blocks retry, even if external API timed out.
    return select(catalog, receipts, dispatched, artifact_list)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    tree = gh("git/trees/render-ledger?recursive=1")
    if tree.get("truncated"):
        raise RuntimeError("Ledger tree truncated; do not risk duplicate publishing")
    all_paths = [x["path"] for x in tree.get("tree", []) if x.get("type") == "blob"]
    receipt_paths = [p for p in all_paths
                     if p.startswith("render-receipts/") and p.endswith(".json")]
    receipts = []
    for path in receipt_paths:
        entry = ledger.api(path)
        if not entry:
            raise RuntimeError("Missing ledger receipt, no publication")
        decoded = ledger.decode_receipt(entry)
        receipts.append(decoded)
    catalog = json.loads(Path(__file__).with_name("episodes.json").read_text("utf8"))
    artifacts = []
    for page in range(1, 7):
        result = gh("actions/artifacts?per_page=100&page=" + str(page))
        artifacts.extend(result.get("artifacts", []))
        if len(result.get("artifacts", [])) < 100:
            break
    else:
        raise RuntimeError("More than 600 artifacts: refuse incomplete inventory")
    selected = select_for_buffer(catalog, receipts, artifacts, all_paths)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if selected:
        run, slug, name = selected
        args.output.write_text("has_job=true\nepisode=" + slug + "\nrender_id=" +
                               str(run) + "\nartifact_name=" + name + "\n", encoding="utf8")
        print("BUFFER_BACKLOG_VERIFIED", slug, "render", run)
    else:
        args.output.write_text("has_job=false\n", encoding="utf8")
        print("BUFFER_BACKLOG_EMPTY: no approved, unique, high-quality unpublished MP4")


if __name__ == "__main__":
    main()
