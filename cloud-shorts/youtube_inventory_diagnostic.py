#!/usr/bin/env python3
"""Read-only uploaded-video playlist diagnostics for safe direct scheduling.

Prints only counts, no video IDs, OAuth token values, filenames or private
metadata. Never modifies YouTube or starts an upload.
"""
from __future__ import annotations
from collections import Counter
import os
import sys

from youtube_upload import authenticated_api, verify_channel

MAX_PAGES = 25

def main():
    api=authenticated_api()
    verified=verify_channel(api)
    result=api.channels().list(part="id,contentDetails,statistics",mine=True).execute()
    channels=result.get("items") or []
    if len(channels)!=1 or channels[0].get("id")!=verified:
        raise RuntimeError("MULTIPLE_OR_INCORRECT_CHANNELS")
    uploads=((channels[0].get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads")
    if not uploads:
        raise RuntimeError("NO_YOUTUBE_UPLOAD_PLAYLIST")
    cursor=None
    seen=set()
    duplicate_count=0
    invalid_count=0
    deleted_or_inaccessible=0
    recorded_pages=0
    statuses=Counter()
    declared_total=None
    while recorded_pages < MAX_PAGES:
        args={"playlistId":uploads,"part":"contentDetails","maxResults":50}
        if cursor:
            args["pageToken"]=cursor
        data=api.playlistItems().list(**args).execute()
        pagesize=len(data.get("items") or [])
        declared_total=(data.get("pageInfo") or {}).get("totalResults",declared_total)
        ids=[]
        for row in data.get("items") or []:
            ident=str((row.get("contentDetails") or {}).get("videoId") or "")
            if len(ident)!=11:
                invalid_count+=1
                continue
            if ident in seen:
                duplicate_count+=1
                continue
            seen.add(ident)
            ids.append(ident)
        if ids:
            matches=api.videos().list(part="id,status,snippet",id=",".join(ids)).execute().get("items",[])
            deleted_or_inaccessible+=len(ids)-len({x.get("id") for x in matches})
            for item in matches:
                s=item.get("status") or {}
                statuses[(s.get("privacyStatus") or "?")+"_scheduled" if s.get("publishAt") else (s.get("privacyStatus") or "?")]+=1
        recorded_pages+=1
        cursor=data.get("nextPageToken")
        print("PAGE",recorded_pages,"items",pagesize,"new_video_ids",len(ids),
              "dup_total",duplicate_count,"invalid_total",invalid_count,
              "missing_details_total",deleted_or_inaccessible,
              "next_page",bool(cursor),flush=True)
        if not cursor:
            break
    if cursor:
        raise RuntimeError("INVENTORY_EXCEEDED_MAX_PAGES")
    print("INVENTORY_DIAGNOSTIC_SUMMARY",
          "pages",recorded_pages,"declared_total",declared_total,
          "distinct_video_ids",len(seen),
          "duplicate_playlist_entries",duplicate_count,
          "malformed_video_ids",invalid_count,
          "unavailable_statuses",deleted_or_inaccessible,
          "privacy_counts",dict(statuses),flush=True)
    print("NO_YOUTUBE_MUTATION_OR_UPLOAD",flush=True)
    return 0

if __name__=="__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("YOUTUBE_INVENTORY_READONLY_STOPPED",type(exc).__name__,
              str(exc)[:130],file=sys.stderr)
        sys.exit(1)
