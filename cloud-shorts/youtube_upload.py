#!/usr/bin/env python3
"""Upload reviewed Shorts through the official YouTube Data API, not Publora.

Secrets belong in GitHub Actions secrets, never this repository.
Public and scheduled uploads follow YouTube's current Data API policies.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timezone

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
CHUNK = 8 * 1024 * 1024
TRANSIENT = {429, 500, 502, 503, 504}

def required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing Google OAuth configuration: {name}")
    return value

def fingerprint(path):
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            sha.update(block)
    return sha.hexdigest()

def clean_description(value):
    """No external links in public description. Source provenance stays internal."""
    out = []
    for line in str(value).splitlines():
        if re.search(r"(?i)https?://|www\.|pexels\.com", line):
            continue
        if re.search(r"(?i)^\s*(кадры|видео|источники|footage|source|credits)\s*:.*(pexels|cottonbro)", line):
            continue
        out.append(line.strip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()[:4900]

def build_body(metadata, privacy):
    title = str(metadata.get("title", "")).strip()
    description = clean_description(metadata.get("description", ""))
    if not (4 <= len(title) <= 100 and description):
        raise ValueError("Valid YouTube title (4-100 chars) and description required")
    if privacy not in ("private", "unlisted", "public"):
        raise ValueError("Unsupported privacy")
    tags = metadata.get("tags") or ["мото", "shorts"]
    if not isinstance(tags, list) or not all(isinstance(x, str) for x in tags):
        raise ValueError("Tags must be strings")
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": [s.strip() for s in tags[:18] if s.strip()],
            "categoryId": "2",
            "defaultLanguage": "ru",
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    if "contains_synthetic_media" in metadata:
        if type(metadata["contains_synthetic_media"]) is not bool:
            raise ValueError("Synthetic media disclosure must be boolean")
        body["status"]["containsSyntheticMedia"] = metadata["contains_synthetic_media"]
    return body

def preflight(video, metadata, privacy):
    if not video.is_file() or video.suffix.lower() != ".mp4":
        raise ValueError("An existing MP4 is required")
    if not (100_000 <= video.stat().st_size <= 150 * 1024 * 1024):
        raise ValueError("MP4 must be 100 KB to 150 MB for this Shorts workflow")
    data = json.loads(metadata.read_text(encoding="utf-8-sig"))
    return build_body(data, privacy), fingerprint(video)

def authenticated_api():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None,
        refresh_token=required_env("YOUTUBE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=required_env("YOUTUBE_CLIENT_ID"),
        client_secret=required_env("YOUTUBE_CLIENT_SECRET"),
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)

def verify_channel(api):
    expected = required_env("YOUTUBE_EXPECTED_CHANNEL_ID")
    if not re.fullmatch(r"UC[a-zA-Z0-9_-]{22}", expected):
        raise RuntimeError("YOUTUBE_EXPECTED_CHANNEL_ID is invalid")
    channels = api.channels().list(part="id,snippet", mine=True).execute().get("items", [])
    actual = [ch.get("id") for ch in channels]
    if expected not in actual:
        raise RuntimeError(f"Wrong channel: expected {expected}, authenticated: {actual}. Upload blocked.")
    return expected

def upload(api, body, video):
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=CHUNK, resumable=True)
    request = api.videos().insert(
        part="snippet,status", body=body, media_body=media, notifySubscribers=False
    )
    response = None
    errors = 0
    while response is None:
        try:
            progress, response = request.next_chunk()
            errors = 0
            if progress:
                print(f"UPLOAD_PROGRESS {progress.progress() * 100:.1f}%")
        except HttpError as exc:
            if exc.resp.status not in TRANSIENT or errors >= 5:
                raise RuntimeError(f"YouTube upload failed HTTP {exc.resp.status}") from None
            errors += 1
            time.sleep(min(20, 2 ** errors))
        except (ConnectionError, TimeoutError) as exc:
            if errors >= 5:
                raise RuntimeError("Upload connection failed; check channel before retry") from exc
            errors += 1
            time.sleep(min(20, 2 ** errors))
    if not response or not response.get("id"):
        raise RuntimeError("YouTube upload returned no video ID")
    return response["id"]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    parser.add_argument("--receipt", type=Path, default=Path("upload_receipt.json"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-schedule", action="store_true",
                        help="Verify live YouTube queue and OAuth without uploading")
    parser.add_argument("--schedule-next", action="store_true",
                        help="Private-first upload, scheduled from real YouTube inventory")
    args = parser.parse_args()
    body, sha = preflight(args.video, args.metadata, args.privacy)
    if args.schedule_next and args.privacy != "private":
        raise ValueError("Scheduled videos must remain private until publishAt")
    if args.check_schedule and not args.schedule_next:
        raise ValueError("Schedule check requires --schedule-next")
    print("VALIDATED", args.video.name, sha[:14], body["snippet"]["title"])
    print("DESCRIPTION_LINKS", bool(re.search(r"https?://|www\.", body["snippet"]["description"])))
    if args.dry_run:
        print("DRY_RUN_OK; no credentials needed; nothing uploaded")
        return
    approved_metadata = json.loads(args.metadata.read_text(encoding="utf-8-sig"))
    if approved_metadata.get("reviewed_for_direct_youtube_upload") is not True:
        raise RuntimeError("LIVE_UPLOAD_REQUIRES_INDEPENDENT_MP4_QA_PROOF")
    if args.check_schedule:
        from direct_schedule import next_verified_slot
        api = authenticated_api()
        verify_channel(api)
        slot = next_verified_slot(api)
        print("YOUTUBE_QUEUE_HAS_ROOM_FOR_ONE_VERIFIED_SLOT", slot)
        return
    # Prevent known duplicates in this invocation's persisted workspace.
    channel = required_env("YOUTUBE_EXPECTED_CHANNEL_ID")
    if args.receipt.exists():
        old = json.loads(args.receipt.read_text(encoding="utf-8"))
        if old.get("sha256") == sha and old.get("channel_id") == channel and old.get("video_id"):
            print("ALREADY_UPLOADED", "https://www.youtube.com/watch?v=" + old["video_id"])
            return
    api = authenticated_api()
    channel = verify_channel(api)
    scheduled_at = None
    if args.schedule_next:
        from direct_schedule import next_verified_slot
        scheduled_at = next_verified_slot(api)
        body["status"]["publishAt"] = scheduled_at
        print("YOUTUBE_SCHEDULE_SLOT_VERIFIED", scheduled_at)
    video_id = upload(api, body, args.video)
    receipt = {
        "sha256": sha, "channel_id": channel, "video_id": video_id,
        "privacy_requested": args.privacy, "public_visibility_verified": False,
        "scheduled_at": scheduled_at, "schedule_readback_verified": False,
        "youtube_url": "https://www.youtube.com/watch?v=" + video_id,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.receipt.with_suffix(".tmp")
    tmp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(args.receipt)
    print("UPLOAD_ACKNOWLEDGED", receipt["youtube_url"])
    if scheduled_at:
        # Never retry an upload on an uncertain outcome. The upload-guard
        # reservation remains locked when the schedule cannot be confirmed.
        for _ in range(3):
            result = api.videos().list(part="id,status", id=video_id).execute()
            entries = result.get("items", [])
            if len(entries) == 1 and entries[0].get("id") == video_id:
                status = entries[0].get("status") or {}
                actual = status.get("publishAt")
                try:
                    a = datetime.fromisoformat(actual.replace("Z", "+00:00"))
                    expected = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
                    matched = (a.astimezone(timezone.utc) == expected.astimezone(timezone.utc))
                except (ValueError, AttributeError, TypeError):
                    matched = False
                if status.get("privacyStatus") == "private" and matched:
                    receipt["schedule_readback_verified"] = True
                    tmp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
                    tmp.replace(args.receipt)
                    print("YOUTUBE_SCHEDULE_READBACK_VERIFIED", video_id, scheduled_at)
                    break
            time.sleep(2)
        if not receipt["schedule_readback_verified"]:
            raise RuntimeError("YOUTUBE_SCHEDULE_READBACK_UNCERTAIN: reconcile Video ID before any retry")
    print("Check processing status at YouTube; public visibility is not yet proven.")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("UPLOAD_STOPPED:", str(exc), file=sys.stderr)
        sys.exit(1)
