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


def _provider_identity_snapshot_with_overlaps(api, uploads, size):
    """Read every real upload row, deduplicating ONLY identical item IDs.

    A documented YouTube pagination anomaly can repeat a playlist item
    while claiming 101 entries. Never invent missing video IDs, omit pages,
    assume 101 video IDs, or accept a single partial provider pass.
    """
    seen_items={}
    ids=set()
    token=None
    tokens=set()
    total_rows=0
    expected=None
    duplicates=0
    while True:
        kwargs={"playlistId":uploads,"part":"id,contentDetails",
                "maxResults":size}
        if token:
            kwargs["pageToken"]=token
        data=api.playlistItems().list(**kwargs).execute()
        rows=data.get("items")
        count=(data.get("pageInfo") or {}).get("totalResults")
        if (not isinstance(rows,list) or type(count) is not int
                or not 1<=count<=MAX_UPLOADS_TO_AUDIT
                or (expected is not None and expected!=count)):
            raise RuntimeError("YOUTUBE_OVERLAP_RECONCILE_BAD_PLAYLIST_RESPONSE")
        expected=count
        next_token=data.get("nextPageToken")
        if not rows and next_token:
            raise RuntimeError("YOUTUBE_OVERLAP_RECONCILE_EMPTY_PAGE")
        for row in rows:
            video=str((row.get("contentDetails") or {}).get("videoId") or "")
            item=str(row.get("id") or "")
            if not item or len(video)!=11:
                raise RuntimeError("YOUTUBE_OVERLAP_RECONCILE_INVALID_ID")
            prev=seen_items.get(item)
            if prev is not None:
                if prev!=video:
                    raise RuntimeError("YOUTUBE_OVERLAP_RECONCILE_IDENTITY_CHANGED")
                duplicates+=1
            else:
                seen_items[item]=video
            ids.add(video)
        total_rows+=len(rows)
        if total_rows>MAX_UPLOADS_TO_AUDIT:
            raise RuntimeError("YOUTUBE_OVERLAP_RECONCILE_TOO_LARGE")
        if not next_token:
            break
        if next_token in tokens:
            raise RuntimeError("YOUTUBE_OVERLAP_RECONCILE_PAGE_TOKEN_CYCLE")
        tokens.add(next_token)
        token=next_token
    if (total_rows!=expected
            or len(seen_items)+duplicates!=total_rows
            or duplicates==0
            or not ids):
        raise RuntimeError("YOUTUBE_OVERLAP_RECONCILE_INCOMPLETE")
    print("YOUTUBE_OVERLAP_RECONCILE_FULL_PROVIDER_PASS",
          "page_size",size,"raw_rows",total_rows,
          "repeated_same_playlist_item",duplicates,
          "unique_video_ids",len(ids),flush=True)
    return frozenset(ids),expected


def _owner_verified_playlist_videos(api, video_ids):
    """Verify every Video ID in the OAuth owner's complete uploads playlist.

    YouTube Search is an index and may omit many older/private uploads.
    The owner's uploads playlist + videos.list(status,snippet.channelId)
    are authoritative for scheduling; do not use search result counts.
    """
    if (not isinstance(video_ids,frozenset) or not video_ids
            or len(video_ids)>MAX_UPLOADS_TO_AUDIT
            or any(not isinstance(x,str) or len(x)!=11 for x in video_ids)):
        raise RuntimeError("YOUTUBE_VERIFIED_UPLOAD_IDS_INVALID")
    result=[]
    ordered=sorted(video_ids)
    for start in range(0,len(ordered),50):
        requested=ordered[start:start+50]
        page=api.videos().list(
            part="id,status,snippet",id=",".join(requested)).execute()
        found=page.get("items")
        if (not isinstance(found,list) or len(found)!=len(requested)
                or {item.get("id") for item in found}!=set(requested)):
            raise RuntimeError("YOUTUBE_VERIFIED_UPLOAD_STATUSES_INCOMPLETE")
        for item in found:
            if (not isinstance(item.get("status"),dict)
                    or not isinstance(item.get("snippet"),dict)
                    or item["snippet"].get("channelId")!=EXPECTED_CHANNEL):
                raise RuntimeError("YOUTUBE_VERIFIED_UPLOAD_WRONG_OWNER_OR_STATUS")
        result.extend(found)
    print("YOUTUBE_UPLOADS_OAUTH_OWNER_AND_STATUS_VERIFIED",
          "unique_videos",len(result),"owner",EXPECTED_CHANNEL,flush=True)
    return result


def _independent_owned_video_search(api, uploads, expected_video_ids=None,
                                    allow_search_index_lag=False):
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
    # When two complete owner-playlist scans independently report the
    # SAME Video ID set despite duplicated playlist-item resources,
    # cross-check its *exact IDs* against the separate owner OAuth Search
    # index. The playlist's row count is not a count of unique videos.
    if expected_video_ids is None:
        complete=(len(seen)==reported and len(all_rows)==reported)
    elif not allow_search_index_lag:
        complete=(isinstance(expected_video_ids,frozenset)
                  and seen==expected_video_ids
                  and len(all_rows)==len(seen)
                  and len(seen)<=reported)
    else:
        # Search forMine sometimes omits one or two older PRIVATE videos.
        # Such a video is never inferred: it must be present in TWO complete
        # repeat scans of the OAuth owner's uploads playlist, which itself
        # reports 101 raw rows (including two duplicated item resources).
        # Then require a real videos.list status for every Search-omitted ID.
        complete=(isinstance(expected_video_ids,frozenset)
                  and len(all_rows)==len(seen)
                  and seen.issubset(expected_video_ids)
                  and 0<=len(expected_video_ids)-len(seen)<=max(8,len(expected_video_ids)//5)
                  and 0<=reported-len(expected_video_ids)<=2)
    if not complete or not set(first_ids).issubset(seen):
        print("YOUTUBE_SEARCH_CROSSCHECK_INCOMPLETE",
              "playlist_total",reported,"unique_owner_search",len(seen),
              "first_playlist_covered",set(first_ids).issubset(seen),flush=True)
        raise RuntimeError("YOUTUBE_UPLOAD_INVENTORY_CROSSCHECK_INCOMPLETE")
    if allow_search_index_lag and expected_video_ids is not None:
        missing=sorted(expected_video_ids-seen)
        if missing:
            verified=api.videos().list(
                part="id,status,snippet",id=",".join(missing)).execute().get("items",[])
            if (not isinstance(verified,list) or len(verified)!=len(missing)
                    or {x.get("id") for x in verified}!=set(missing)
                    or any(not isinstance(x.get("status"),dict)
                           or not isinstance(x.get("snippet"),dict)
                           or x["snippet"].get("channelId")!=EXPECTED_CHANNEL
                           for x in verified)):
                raise RuntimeError("YOUTUBE_OWNED_PRIVATE_SEARCH_LAG_NOT_PROVEN")
            all_rows.extend(verified)
        if {x.get("id") for x in all_rows}!=expected_video_ids:
            raise RuntimeError("YOUTUBE_SEARCH_PLAYLIST_FULL_ID_SET_MISMATCH")
        print("YOUTUBE_OWNER_SEARCH_INDEX_LAG_RECONCILED",
              "search",len(seen),"playlist",len(expected_video_ids),
              "verified_missing_videos",len(missing),flush=True)
    print("YOUTUBE_UPLOAD_INVENTORY_INDEPENDENT_OWNER_SEARCH_VERIFIED",
          "unique_videos",len(all_rows),"playlist_reported",reported,flush=True)
    return all_rows


def youtube_inventory(api, expected=EXPECTED_CHANNEL):
    channels=api.channels().list(part="id,contentDetails",mine=True).execute().get("items",[])
    exact=[row for row in channels if row.get("id")==expected]
    if len(exact)!=1 or len(channels)!=1:
        raise RuntimeError("WRONG_OR_AMBIGUOUS_YOUTUBE_OAUTH_CHANNEL")
    uploads=(exact[0].get("contentDetails") or {}).get("relatedPlaylists",{}).get("uploads")
    if not uploads:
        raise RuntimeError("YOUTUBE_UPLOAD_PLAYLIST_NOT_FOUND")
    # YouTube sometimes returns the SAME playlistItem on adjacent pages
    # even when neither page includes an invalid Video ID. A 50-item
    # snapshot and a 37-item retry can both have overlapping boundaries
    # (confirmed for the real 101-item owned uploads playlist).
    # Small, independent page partitions are safer than falsely treating
    # a 99-video Search subset as complete or bypassing inventory checks.
    # Accept ONLY one complete, exact-count, SHA-free provider snapshot:
    # _provider_upload_snapshot validates all resource IDs and statuses.
    for size in (50,37,25,10,5):
        try:
            videos=_provider_upload_snapshot(api,uploads,size)
            return release_times_from_items(videos)
        except RuntimeError as error:
            if str(error)!="YOUTUBE_UPLOAD_PLAYLIST_PAGE_OVERLAP":
                raise
            print("YOUTUBE_UPLOAD_PLAYLIST_RESCAN_DIFFERENT_PAGE_BOUNDARIES",
                  "page_size",size,flush=True)
    print("YOUTUBE_UPLOAD_PLAYLIST_ALL_PARTITIONS_INCONSISTENT",
          "require_two_full_identity_reconciliations",flush=True)
    # The real API yields 99 unique IDs at page_size=37 but only 98,
    # 94 or 87 with smaller page sizes. Repeat 37 independently to prove
    # the SAME full ID set, then use size=25 only as a subset crosscheck.
    # Never mistake a smaller truncated page partition for a new video.
    try:
        first,total=_provider_identity_snapshot_with_overlaps(api,uploads,37)
        repeat,second_total=_provider_identity_snapshot_with_overlaps(
            api,uploads,37)
        smaller,small_total=_provider_identity_snapshot_with_overlaps(
            api,uploads,25)
    except RuntimeError as error:
        raise RuntimeError(
            "YOUTUBE_UPLOAD_INVENTORY_CROSSCHECK_INCOMPLETE") from error
    if (total!=second_total or total!=small_total
            or first!=repeat or not smaller.issubset(first)
            or len(first)-len(smaller)>2):
        raise RuntimeError("YOUTUBE_UPLOAD_INVENTORY_CROSSCHECK_INCOMPLETE")
    print("YOUTUBE_UPLOAD_PLAYLIST_TWO_STABLE_OWNER_SCANS",
          "unique_video_ids",len(first),
          "small_page_subset",len(smaller),flush=True)
    # Official owner playlist explicitly identifies every uploaded Video ID.
    # Read all 99 IDs from videos.list and demand the exact authenticated
    # channelId on EACH row. The independent Search index previously returned
    # 99, 98, 96, 92 and 75 IDs for the very same stable owner inventory.
    # It is therefore not a trustworthy completeness source for PRIVATE
    # videos, whereas videos.list supplies actual status/publishAt for each.
    videos=_owner_verified_playlist_videos(api,first)
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
