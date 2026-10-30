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
from production_readiness import inventory
from editorial_novelty import is_repeated_visual_formula


def select_for_buffer(catalog, receipts, artifact_list, tree_paths):
    dispatched = {Path(p).stem for p in tree_paths if
                  (p.startswith("publication-receipts/") or
                   p.startswith("buffer-publication-receipts/"))
                  and p.endswith(".json")}
    # Each active reservation blocks retry, even if external API timed out.
    return select(catalog, receipts, dispatched, artifact_list)


def explain_unavailable(catalog, receipts, artifacts, paths):
    """Explain *why* zero uploadable MP4 exist; no hidden green success."""
    by_id = {receipt.get("id"): receipt for receipt in receipts}
    produced = {
        ep["id"] for ep in catalog["episodes"]
        if by_id.get(ep["id"], {}).get("state") == "preview_ready"
    }
    all_ids = {Path(p).stem for p in paths
               if p.startswith("render-receipts/") and p.endswith(".json")}
    stock = inventory(catalog, all_ids)
    denied = [
        ep for ep in catalog["episodes"]
        if ep.get("editorial_rejected") is True
        or ep.get("visual_review_failed") is True
        or is_repeated_visual_formula(ep, catalog["episodes"])
    ]
    pending_private = [
        ep["id"] for ep in catalog["episodes"]
        if ep["id"] in produced
        and ep.get("auto_publish") is not True
        and ep not in denied
    ]
    unreviewed_v3 = [
        ep["id"] for ep in catalog["episodes"]
        if ep["id"] in produced and ep.get("auto_publish") is True
        and int(ep.get("visual_director_version") or 0) >= 3
        and (ep.get("visual_revision_status") != "assistant_checked_passed"
             or not ep.get("scene_script_anchors"))
    ]
    return {
        "verified_mp4_previews": len(produced),
        "approved_for_automatic_release": len([
            ep for ep in catalog["episodes"]
            if ep["id"] in produced and ep.get("auto_publish") is True
            and ep not in denied
        ]),
        "private_preview_ids": pending_private[:25],
        "rejected_or_repeated_visual_ids": [ep["id"] for ep in denied][:25],
        "awaiting_actual_v3_visual_review_ids": unreviewed_v3[:25],
        "unrendered_scripts_no_original_deep": stock["unrendered_missing_original_deep"],
        "unrendered_real_deep_ready": stock["unrendered_verified_deep_originals"],
        "autonomous_deep_tts_connected": stock["has_autonomous_deep_tts"],
        "not_a_buffer_api_error": True,
        "cause": "NO_EDITORIALLY_APPROVED_VERIFIED_NEW_MP4",
    }


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
        reason = explain_unavailable(catalog, receipts, artifacts, all_paths)
        print("BUFFER_BACKLOG_EMPTY", json.dumps(reason, ensure_ascii=False), flush=True)
        print("::warning::BUFFER_NOT_AUTONOMOUS: no suitable verified new MP4. "
              "Check DEEP TTS, repeated footage and visual signoff.", flush=True)
        summary = os.getenv("GITHUB_STEP_SUMMARY")
        if summary:
            Path(summary).open("a", encoding="utf8").write(
                "\\n## Buffer production blocked\\n\\n"
                + "Unavailable reason: " + reason["cause"] + "\\n\\n"
                + "Unrendered original DEEP audio available: "
                + str(reason["unrendered_real_deep_ready"]) + "\\n\\n"
                + "Scripts with no actual DEEP MP3: "
                + str(reason["unrendered_scripts_no_original_deep"]) + "\\n\\n"
                + "QA MP4s still private: "
                + ", ".join(reason["private_preview_ids"]) + "\\n\\n"
                + "Visually repeated/rejected: "
                + ", ".join(reason["rejected_or_repeated_visual_ids"]) + "\\n"
            )


if __name__ == "__main__":
    main()
