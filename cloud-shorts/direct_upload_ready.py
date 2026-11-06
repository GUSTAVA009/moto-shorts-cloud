#!/usr/bin/env python3
"""Vendor-independent release gate for an actual reviewed MP4 (no upload)."""
import argparse
import json
import re
from pathlib import Path

from publication_safety import publication_allowed
from buffer_autopublish import validate_video, should_disclose_generated_content
from editorial_novelty import is_repeated_visual_formula

HERE = Path(__file__).resolve().parent


def check(episode_id, staged, catalog=None):
    if catalog is None:
        catalog = json.loads((HERE / "episodes.json").read_text(encoding="utf8"))
    entries = [e for e in catalog.get("episodes", []) if e.get("id") == episode_id]
    if not entries:
        # Independent, SHA-pinned owner render is not necessarily a
        # two-stock-clips factory draft. Never loosen historical catalog tests
        # by injecting this distinct production type into episodes.json.
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,99}", episode_id):
            raise ValueError("UNVERIFIED_EPISODE_ID")
        manifest_file = HERE / "release_manifests" / (episode_id + ".json")
        if not manifest_file.is_file():
            raise ValueError("UNVERIFIED_EPISODE_ID")
        manifest = json.loads(manifest_file.read_text(encoding="utf8"))
        ep = manifest.get("episode") or {}
        if (manifest.get("episode_id") != episode_id
                or ep.get("id") != episode_id
                or ep.get("editorial_format") != "owner_original_single_source_explainer_v4"
                or manifest.get("final_mp4_sha256") != ep.get("final_video_sha256")
                or not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("final_mp4_sha256") or ""))):
            raise ValueError("IMMUTABLE_OWNER_RELEASE_MANIFEST_MISMATCH")
        entries = [ep]
        catalog = {"episodes": [*catalog.get("episodes", []), ep]}
    if len(entries) != 1:
        raise ValueError("UNVERIFIED_EPISODE_ID")
    episode = entries[0]
    if episode.get("auto_publish") is not True:
        raise ValueError("EPISODE_NOT_APPROVED_FOR_PUBLICATION")
    if is_repeated_visual_formula(episode, catalog["episodes"]):
        raise ValueError("REPEATED_VISUAL_FORMULA_NOT_APPROVED")
    staged = Path(staged)
    video = staged / (episode_id + ".mp4")
    paths = {"meta": staged / "publication.json", "voice": staged / "voice_qa.json",
             "mixed": staged / "mixed_audio_qa.json", "visual": staged / "visual_qa.json"}
    if not video.is_file() or any(not p.is_file() for p in paths.values()):
        raise ValueError("FINAL_MP4_OR_INDEPENDENT_QA_MISSING")
    meta = json.loads(paths["meta"].read_text(encoding="utf8"))
    voice = json.loads(paths["voice"].read_text(encoding="utf8"))
    mixed = json.loads(paths["mixed"].read_text(encoding="utf8"))
    visual = json.loads(paths["visual"].read_text(encoding="utf8"))
    if visual.get("passed") is not True:
        raise ValueError("FINAL_MP4_VISUAL_QA_FAILED")
    voice["mixed_audio"] = mixed
    publication_allowed(episode, meta, voice, video)
    validate_video(video)
    approved = dict(meta)
    approved["contains_synthetic_media"] = should_disclose_generated_content(episode)
    approved["reviewed_for_direct_youtube_upload"] = True
    return approved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode", required=True)
    parser.add_argument("--staged", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    meta = check(args.episode, args.staged)
    args.output.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf8")
    print("DIRECT_MP4_QA_VERIFIED", args.episode)


if __name__ == "__main__":
    main()
