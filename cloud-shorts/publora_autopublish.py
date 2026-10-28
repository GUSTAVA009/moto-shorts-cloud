#!/usr/bin/env python3
"""Publish one independently QA-checked original MP4 through the official Publora REST API.

Secrets: PUBLORA_API_KEY in GitHub Actions secrets. No direct YouTube OAuth or
web scraping. GitHub's render-ledger contains a fail-closed reservation BEFORE
the create-post call; unknown results are never blindly retried.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

import preview_queue as ledger

API = "https://api.publora.com/api/v1"
EXPECTED_CHANNEL = "youtube-UCS0QCodPcFBTjMt4ioEWOUw"
SHA_RE = re.compile(r"^[a-f0-9]{64}$")


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def receipt_path(episode):
    ledger.item_path(episode)  # validate slug
    return "publication-receipts/" + episode + ".json"


def publication_allowed(episode, meta, qa, video):
    if not episode.get("auto_publish") is True:
        raise ValueError("This episode was not explicitly queued for automatic release")
    if meta.get("episode_id") != episode["id"] or qa.get("episode_id") != episode["id"]:
        raise ValueError("Metadata/ASR episode mismatch; do not upload")
    if qa.get("passed") is not True or qa.get("status") != "passed":
        raise ValueError("Russian voice QA incomplete: no automatic release")
    if (qa.get("lexical_coverage", 0) < .79 or qa.get("ending_coverage", 0) < .60
            or qa.get("final_word_present") is not True):
        raise ValueError("Missing or clipped Russian narration")
    if not video.is_file() or not 100000 <= video.stat().st_size <= 150*1024*1024:
        raise ValueError("Invalid MP4 file or unexpected size")
    if video.suffix.lower() != ".mp4" or not meta.get("title") or not meta.get("description"):
        raise ValueError("Invalid upload metadata")
    if len(meta["title"]) > 100 or any(s in meta["description"].lower() for s in ("https://", "www.")):
        raise ValueError("Illegal title or external links in description")
    if not episode.get("footage") or any(s.get("license") != "Pexels License"
                                      for s in episode["footage"]):
        raise ValueError("Unverified commercial footage rights")
    series = episode.get("episode_series")
    if series and series.get("historical_reconstruction"):
        refs = episode.get("editorial_references") or []
        if (len(set(refs)) < 2 or any(not str(u).startswith("https://") for u in refs)
                or "иллюстративные" not in meta["description"].casefold()):
            raise ValueError("Real-event documentary lacks independent sources or illustration disclosure")
    return True


def http(method, path, payload=None, idem=None):
    secret = os.environ.get("PUBLORA_API_KEY", "").strip()
    if not secret or not secret.startswith("sk_"):
        raise RuntimeError("PUBLORA_API_KEY not configured; no publish")
    headers = {"x-publora-key": secret, "Content-Type": "application/json",
               "User-Agent": "GUSTAVA-Shorts-Factory/1.0"}
    if idem:
        headers["Idempotency-Key"] = idem
    body = json.dumps(payload, ensure_ascii=False).encode("utf8") if payload is not None else None
    req = urllib.request.Request(API + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=75) as r:
            return json.loads(r.read(1048576).decode("utf8"))
    except urllib.error.HTTPError as ex:
        # Do not log credentials, request bodies, signed upload links or raw errors.
        raise RuntimeError("Publora API refused request HTTP " + str(ex.code)) from None


def check_connection():
    response = http("GET", "/platform-connections")
    connections = response.get("connections", []) if isinstance(response, dict) else []
    if not any(c.get("platformId") == EXPECTED_CHANNEL and
               c.get("connectionStatus") == "active" and
               c.get("tokenStatus") in ("valid", "expiring_soon", None)
               for c in connections):
        raise RuntimeError("Expected GUSTAVA YouTube channel not active in Publora")
    return True


def record(path, state, sha=None):
    previous = ledger.api(path)
    if previous and not sha:
        raise RuntimeError("Existing publication reservation: no blind duplicate retry")
    ledger.store(path, state, "Publication state " + state["state"] +
                 " " + state["episode"], old_sha=sha)


def update(path, state):
    current = ledger.api(path)
    if current is None or not current.get("sha"):
        raise RuntimeError("Publication ledger disappeared")
    record(path, state, current["sha"])


def upload_file(group_id, video, basename):
    r = http("POST", "/get-upload-url",
             {"fileName": basename, "contentType": "video/mp4",
              "type": "video", "postGroupId": group_id})
    url = r.get("uploadUrl")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise RuntimeError("Publora did not provide a secure signed upload URL")
    req = urllib.request.Request(
        url, data=video.read_bytes(), headers={"Content-Type": "video/mp4"},
        method="PUT")
    with urllib.request.urlopen(req, timeout=180) as response:
        if response.status not in (200, 201, 204):
            raise RuntimeError("Signed storage upload was not accepted")
    media_id = r.get("mediaId")
    if media_id:
        try:
            http("POST", "/complete-media/" + str(media_id))
        except RuntimeError:
            # Completion can be asynchronous; check real post media state below.
            pass
    for _ in range(8):
        post = http("GET", "/get-post/" + group_id)
        media = post.get("media", [])
        if any(m.get("status") == "ready" and
               (not media_id or m.get("mediaId") == media_id) for m in media):
            return
        if any(m.get("status") == "failed" for m in media):
            raise RuntimeError("Publora media failed validation")
        time.sleep(5)
    raise RuntimeError("Publora media has not reached ready; keep draft")


def prior_series_episode(episode):
    """Historical chapters must appear in sequence, never part 5 before part 4."""
    series = episode.get("episode_series")
    if not series:
        return None
    chapter = int(series.get("chapter", 0))
    if chapter < 1 or chapter > int(series.get("chapter_total", 0)):
        raise ValueError("Invalid documentary chapter")
    if chapter == 1:
        return None
    import re as _re
    eid = str(episode["id"])
    if not _re.search(r"-e\\d{2}$", eid):
        raise ValueError("Documentary filename must end in chronological chapter")
    return eid[:-2] + f"{chapter-1:02d}"


def enforce_series_release_order(episode):
    previous = prior_series_episode(episode)
    if previous is None:
        return
    entry = ledger.api(receipt_path(previous))
    if not entry or not entry.get("content"):
        raise RuntimeError("SERIES_PREDECESSOR_NOT_PUBLISHED: earlier episode receipt missing")
    import base64
    receipt = json.loads(base64.b64decode(entry["content"]))
    group = receipt.get("post_group_id")
    if not isinstance(group, str) or not re.fullmatch(r"[0-9a-fA-F]{24}", group):
        raise RuntimeError("SERIES_PREDECESSOR_NOT_PUBLISHED: earlier post ID not confirmed")
    remote = http("GET", "/get-post/" + group)
    if remote.get("status") != "published" or not any(
            x.get("status") == "published" for x in remote.get("posts", [])):
        raise RuntimeError("SERIES_PREDECESSOR_NOT_PUBLISHED: wait for earlier episode on YouTube")


def publish(episode, meta, qa, video, dry_run=False):
    publication_allowed(episode, meta, qa, video)
    video_sha = file_sha256(video)
    path = receipt_path(episode["id"])
    if dry_run:
        return {"dry_run": True, "episode": episode["id"], "sha256": video_sha,
                "publication_allowed": True}
    if os.environ.get("PUBLORA_AUTO_PUBLISH_ENABLED", "").lower() != "true":
        return {"skipped": "PUBLORA_AUTO_PUBLISH_ENABLED is not true"}
    if not os.environ.get("PUBLORA_API_KEY"):
        return {"skipped": "PUBLORA_API_KEY is not installed in GitHub Secrets"}
    check_connection()
    enforce_series_release_order(episode)
    if ledger.api(path):
        return {"skipped": "Publication receipt already exists; manual reconciliation if incomplete"}
    reservation = {"episode": episode["id"], "sha256": video_sha,
                   "run_id": os.environ.get("GITHUB_RUN_ID", ""),
                   "state": "reserved",
                   "warning": "Never repeat this logical upload after an unknown response"}
    record(path, reservation)
    draft_payload = {
        "content": meta["description"],
        "platforms": [EXPECTED_CHANNEL],
        "platformSettings": {
            "youtube": {"title": meta["title"], "privacy": "public",
                        "madeForKids": False, "tags": meta.get("tags", ["мото", "shorts"])}
        }
    }
    draft_key = "gustava-" + episode["id"] + "-" + video_sha[:16] + "-draft-v1"
    try:
        created = http("POST", "/create-post", draft_payload, draft_key)
        group_id = created.get("postGroupId")
        if not isinstance(group_id, str) or not re.fullmatch(r"[0-9a-fA-F]{24}", group_id):
            raise RuntimeError("Draft response missing identifier; preserve reservation")
        reservation.update({"state": "draft_created", "post_group_id": group_id})
        update(path, reservation)
        upload_file(group_id, video, episode["id"] + ".mp4")
        reservation["state"] = "media_ready"
        update(path, reservation)
        # Record intent before external publication. If the response is lost,
        # we reconcile against the known post ID rather than create a duplicate.
        reservation["state"] = "publish_requested"
        update(path, reservation)
        http("PUT", "/update-post/" + group_id, {"publishNow": True},
             "gustava-" + episode["id"] + "-" + video_sha[:16] + "-publish-v1")
        post = http("GET", "/get-post/" + group_id)
        state = post.get("status", "pending")
        reservation.update({"state": "submitted", "publora_status": state})
        update(path, reservation)
        return {"submitted": True, "episode": episode["id"],
                "post_group_id": group_id, "publora_status": state}
    except Exception:
        # No automatic retries: state in GitHub identifies where to reconcile.
        raise


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--episode", required=True)
    p.add_argument("--catalog", type=Path, default=Path(__file__).with_name("episodes.json"))
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--metadata", type=Path, required=True)
    p.add_argument("--voice-qa", type=Path, required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    eps = json.loads(args.catalog.read_text(encoding="utf8"))["episodes"]
    episode = next((e for e in eps if e["id"] == args.episode), None)
    if episode is None:
        raise SystemExit("Episode not found")
    qa = json.loads(args.voice_qa.read_text(encoding="utf8"))
    meta = json.loads(args.metadata.read_text(encoding="utf8"))
    result = publish(episode, meta, qa, args.video, args.dry_run)
    print("PUBLISH_RESULT", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
