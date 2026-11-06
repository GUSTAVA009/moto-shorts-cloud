#!/usr/bin/env python3
"""Read YouTube-owned upload inventory before selecting a safe 15/day release slot.

Read only. All timestamps remain provider-backed; scripts and Github receipts are
not substituted for an actual YouTube scheduled/public video.
"""
from __future__ import annotations
from datetime import datetime, timezone
from ten_daily_slots import choose_slot, BASE_POSTS_PER_DAY

EXPECTED_CHANNEL = "UCS0QCodPcFBTjMt4ioEWOUw"
MAX_UPLOADS_TO_AUDIT = 1000


def release_times_from_items(videos):
    """Actual published dates plus scheduled times; private unscheduled is not public."""
    slots = []
    ids = set()
    for video in videos:
        video_id = video.get("id")
        if not video_id or video_id in ids:
            raise RuntimeError("YOUTUBE_UPLOAD_INVENTORY_DUPLICATE_OR_MISSING_ID")
        ids.add(video_id)
        status = video.get("status") or {}
        snippet = video.get("snippet") or {}
        future = status.get("publishAt")
        privacy = status.get("privacyStatus")
        if future:
            if privacy != "private":
                raise RuntimeError("INCONSISTENT_YOUTUBE_SCHEDULED_PRIVACY")
            slots.append({"dueAt": future})
        elif privacy == "public":
            published = snippet.get("publishedAt")
            if not published:
                raise RuntimeError("PUBLIC_YOUTUBE_VIDEO_MISSING_PUBLICATION_TIME")
            slots.append({"dueAt": published})
    return slots


def youtube_inventory(api, expected=EXPECTED_CHANNEL):
    channels = api.channels().list(part="id,contentDetails", mine=True).execute().get("items", [])
    exact = [row for row in channels if row.get("id") == expected]
    if len(exact) != 1 or len(channels) != 1:
        raise RuntimeError("WRONG_OR_AMBIGUOUS_YOUTUBE_OAUTH_CHANNEL")
    uploads = (exact[0].get("contentDetails") or {}).get("relatedPlaylists", {}).get("uploads")
    if not uploads:
        raise RuntimeError("YOUTUBE_UPLOAD_PLAYLIST_NOT_FOUND")
    videos = []
    seen = set()
    page = None
    while True:
        args = {"playlistId": uploads, "part": "contentDetails", "maxResults": 50}
        if page:
            args["pageToken"] = page
        result = api.playlistItems().list(**args).execute()
        batch = result.get("items") or []
        ids = [str((v.get("contentDetails") or {}).get("videoId") or "") for v in batch]
        if (not ids and result.get("nextPageToken")) or any(
                len(v) != 11 or v in seen for v in ids):
            raise RuntimeError("YOUTUBE_UPLOAD_PLAYLIST_INCOMPLETE_OR_DUPLICATE")
        seen.update(ids)
        if ids:
            details = api.videos().list(part="id,status,snippet", id=",".join(ids)).execute().get("items", [])
            if {r.get("id") for r in details} != set(ids):
                raise RuntimeError("YOUTUBE_UPLOAD_STATUSES_INCOMPLETE")
            videos.extend(details)
        page = result.get("nextPageToken")
        if not page:
            break
        if len(videos) >= MAX_UPLOADS_TO_AUDIT:
            raise RuntimeError("YOUTUBE_UPLOAD_INVENTORY_TOO_LARGE_TO_VERIFY")
    return release_times_from_items(videos)


def next_verified_slot(api, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("SCHEDULER_REQUIRES_TIMEZONE")
    events = youtube_inventory(api)
    from ten_daily_slots import parse_date
    queued = sum(parse_date(row["dueAt"]) > now for row in events)
    if queued >= 10:
        raise RuntimeError("YOUTUBE_SCHEDULE_RESERVE_FULL: 10 confirmed future posts already queued")
    # Standard 15 releases/day; a sixteenth catch-up requires explicit approval.
    return choose_slot(events, now=now, max_posts_per_day=BASE_POSTS_PER_DAY,
                       min_lead_minutes=90)
