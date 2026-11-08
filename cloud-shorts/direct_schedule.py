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


def _provider_upload_snapshot(api, playlist_id, page_size):
    """Fetch EVERY playlist item and its status with identity proofs.

    A video can appear twice as different playlist resources, but must never
    be counted twice toward schedule capacity. An overlapping exact resource
    ID indicates pagination drift, NOT a legitimate second playlist item.
    """
    videos=[]
    seen_videos=set()
    seen_items=set()
    total_entries=0
    expected_total=None
    duplicate_video_entries=0
    page=None
    page_tokens=set()
    while True:
        args={"playlistId":playlist_id,"part":"id,contentDetails",
              "maxResults":page_size}
        if page:
            args["pageToken"]=page
        result=api.playlistItems().list(**args).execute()
        batch=result.get("items")
        if not isinstance(batch,list):
            raise RuntimeError("YOUTUBE_UPLOAD_PLAYLIST_INVALID_ITEMS")
        reported=(result.get("pageInfo") or {}).get("totalResults")
        if type(reported) is not int or reported<0 or reported>MAX_UPLOADS_TO_AUDIT:
            raise RuntimeError("YOUTUBE_UPLOAD_PLAYLIST_TOTAL_UNTRUSTED")
        if expected_total is None:
            expected_total=reported
        elif expected_total!=reported:
            raise RuntimeError("YOUTUBE_UPLOAD_PLAYLIST_CHANGED_DURING_SCAN")
        next_page=result.get("nextPageToken")
        if not batch and next_page:
            raise RuntimeError("YOUTUBE_UPLOAD_PLAYLIST_INCOMPLETE_OR_DUPLICATE")
        batch_new=[]
        invalid=0
        overlaps=0
        for row in batch:
            video_id=str((row.get("contentDetails") or {}).get("videoId") or "")
            playlist_item_id=str(row.get("id") or "")
            if len(video_id)!=11 or not playlist_item_id:
                invalid+=1
                continue
            if playlist_item_id in seen_items:
                overlaps+=1
                continue
            seen_items.add(playlist_item_id)
            if video_id in seen_videos:
                duplicate_video_entries+=1
            else:
                seen_videos.add(video_id)
                batch_new.append(video_id)
        total_entries+=len(batch)
        if invalid or overlaps:
            print("YOUTUBE_UPLOAD_PLAYLIST_SAFE_DIAG",
                  "batch",len(batch),
                  "invalid_id_count",invalid,
                  "duplicate_item_count",overlaps,
                  "duplicate_video_entries",duplicate_video_entries,
                  "reported_total",expected_total,
                  "has_next",bool(next_page),flush=True)
            if overlaps and not invalid:
                raise RuntimeError("YOUTUBE_UPLOAD_PLAYLIST_PAGE_OVERLAP")
            raise RuntimeError("YOUTUBE_UPLOAD_PLAYLIST_INCOMPLETE_OR_DUPLICATE")
        if total_entries>MAX_UPLOADS_TO_AUDIT:
            raise RuntimeError("YOUTUBE_UPLOAD_INVENTORY_TOO_LARGE_TO_VERIFY")
        if batch_new:
            details=api.videos().list(part="id,status,snippet",
                                      id=",".join(batch_new)).execute().get("items",[])
            if (not isinstance(details,list) or len(details)!=len(batch_new)
                    or {row.get("id") for row in details}!=set(batch_new)):
                raise RuntimeError("YOUTUBE_UPLOAD_STATUSES_INCOMPLETE")
            videos.extend(details)
        page=next_page
        if not page:
            break
        if page in page_tokens:
            raise RuntimeError("YOUTUBE_UPLOAD_PLAYLIST_PAGE_TOKEN_CYCLE")
        page_tokens.add(page)
    if (expected_total!=total_entries
            or len(seen_items)!=total_entries
            or len(seen_videos)!=len(videos)):
        raise RuntimeError("YOUTUBE_UPLOAD_PLAYLIST_INCOMPLETE_OR_DUPLICATE")
    print("YOUTUBE_UPLOAD_PLAYLIST_IDENTITY_VERIFIED",
          "playlist_items",total_entries,
          "unique_videos",len(seen_videos),
          "duplicate_video_entries",duplicate_video_entries,
          "page_size",page_size,flush=True)
    return videos


def _independent_owned_video_search(api, uploads):
    """Fallback to separate owner-authenticated YouTube Search API if the

    Uploads playlist's own page tokens overlap. Never infer missing IDs or
    schedule from GitHub metadata; Search must enumerate every owned Video ID
    and independently agree with the original playlist's reported count.
    This extra quota is spent only when playlist pagination is contradictory.
    """
    first=api.playlistItems().list(
        playlistId=uploads,part="id,contentDetails",maxResults=50).execute()
    reported=(first.get("pageInfo") or {}).get("totalResults")
    initial=first.get("items")
    if (type(reported) is not int or not 1<=reported<=MAX_UPLOADS_TO_AUDIT
            or not isinstance(initial,list) or len(initial)>50):
        raise RuntimeError("YOUTUBE_INDEPENDENT_SEARCH_UNTRUSTED_PLAYLIST_COUNT")
    first_ids=[]
    for item in initial:
        video_id=str((item.get("contentDetails") or {}).get("videoId") or "")
        if len(video_id)!=11:
            raise RuntimeError("YOUTUBE_INDEPENDENT_SEARCH_BAD_INITIAL_VIDEO_ID")
        first_ids.append(video_id)

    all_rows=[]
    seen=set()
    page_tokens=set()
    token=None
    # forMine + type=video is an official OAuth-scoped channel-owned search.
    # It includes private/scheduled uploads, unlike public-only channel lists.
    while True:
        params={"part":"id","forMine":True,"type":"video",
                "order":"date","maxResults":50}
        if token:
            params["pageToken"]=token
        data=api.search().list(**params).execute()
        results=data.get("items")
        if not isinstance(results,list):
            raise RuntimeError("YOUTUBE_INDEPENDENT_SEARCH_BAD_RESPONSE")
        new_ids=[]
        for item in results:
            ident=item.get("id") or {}
            vid=ident.get("videoId") if isinstance(ident,dict) else None
            kind=ident.get("kind") if isinstance(ident,dict) else None
            if (not isinstance(vid,str) or len(vid)!=11
                    or kind!="youtube#video" or vid in seen):
                raise RuntimeError("YOUTUBE_INDEPENDENT_SEARCH_DUPLICATE_OR_INVALID")
            seen.add(vid)
            new_ids.append(vid)
        if new_ids:
            details=api.videos().list(
                part="id,status,snippet",id=",".join(new_ids)).execute().get("items",[])
            if (not isinstance(details,list) or len(details)!=len(new_ids)
                    or {x.get("id") for x in details}!=set(new_ids)):
                raise RuntimeError("YOUTUBE_INDEPENDENT_SEARCH_STATUSES_INCOMPLETE")
            all_rows.extend(details)
        token=data.get("nextPageToken")
        if not token:
            break
        if token in page_tokens or len(seen)>MAX_UPLOADS_TO_AUDIT:
            raise RuntimeError("YOUTUBE_INDEPENDENT_SEARCH_BAD_PAGINATION")
        page_tokens.add(token)
    # A search index can lag or omit private videos. Never treat a subset as
    # a complete list when another owner API reports more upload records.
    if (len(seen)!=reported or not set(first_ids).issubset(seen)
            or len(all_rows)!=reported):
        print("YOUTUBE_SEARCH_CROSSCHECK_INCOMPLETE",
              "playlist_total",reported,"unique_owner_search",len(seen),
              "first_playlist_covered",set(first_ids).issubset(seen),flush=True)
        raise RuntimeError("YOUTUBE_UPLOAD_INVENTORY_CROSSCHECK_INCOMPLETE")
    print("YOUTUBE_UPLOAD_INVENTORY_INDEPENDENT_OWNER_SEARCH_VERIFIED",
          "unique_videos",len(seen),"playlist_reported",reported,flush=True)
    return all_rows


def youtube_inventory(api, expected=EXPECTED_CHANNEL):
    channels=api.channels().list(part="id,contentDetails",mine=True).execute().get("items",[])
    exact=[row for row in channels if row.get("id")==expected]
    if len(exact)!=1 or len(channels)!=1:
        raise RuntimeError("WRONG_OR_AMBIGUOUS_YOUTUBE_OAUTH_CHANNEL")
    uploads=(exact[0].get("contentDetails") or {}).get("relatedPlaylists",{}).get("uploads")
    if not uploads:
        raise RuntimeError("YOUTUBE_UPLOAD_PLAYLIST_NOT_FOUND")
    try:
        videos=_provider_upload_snapshot(api,uploads,50)
    except RuntimeError as error:
        if str(error)!="YOUTUBE_UPLOAD_PLAYLIST_PAGE_OVERLAP":
            raise
        # A live upload shifted a page boundary mid-scan. Re-read all
        # provider pages with a different size; do not count the overlapped
        # playlist item twice or reserve from an incomplete snapshot.
        print("YOUTUBE_UPLOAD_PLAYLIST_RESCAN_DIFFERENT_PAGE_BOUNDARIES",flush=True)
        try:
            videos=_provider_upload_snapshot(api,uploads,37)
        except RuntimeError as again:
            if str(again)!="YOUTUBE_UPLOAD_PLAYLIST_PAGE_OVERLAP":
                raise
            print("YOUTUBE_UPLOAD_PLAYLIST_TWO_INCONSISTENT_SCANS",
                  "independent_owner_search_required",flush=True)
            videos=_independent_owned_video_search(api,uploads)
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
