#!/usr/bin/env python3
"""One-time PRIVATE YouTube Data API canary. Never schedules or publishes.

Only valid for an explicit workflow_dispatch confirmation. This is a
DIAGNOSTIC, unrelated to approved/editorial Shorts. It is never passed into
the production video queue.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

CHANNEL = "UCS0QCodPcFBTjMt4ioEWOUw"
REPO = "GUSTAVA009/moto-shorts-cloud"
TITLE = "GUSTAVA Factory | PRIVATE API TEST | Do Not Publish"
TAG = "gustava-api-private-canary-v1"
CONFIRM = "GUSTAVA_PRIVATE_CANARY_ONLY"
MAX_PAGES = 20


def authenticate():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    required = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
    if any(not os.getenv(name) for name in required):
        raise RuntimeError("MISSING_OAUTH_SECRETS")
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload",
                "https://www.googleapis.com/auth/youtube.readonly"],
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def inventory(api):
    channels = api.channels().list(part="id,contentDetails", mine=True).execute().get("items", [])
    if [x.get("id") for x in channels] != [CHANNEL]:
        raise RuntimeError("WRONG_OAUTH_YOUTUBE_CHANNEL")
    uploads = channels[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    if not uploads:
        raise RuntimeError("YOUTUBE_UPLOADS_PLAYLIST_MISSING")
    cursor = None
    for page in range(MAX_PAGES):
        opts = {"part":"contentDetails", "playlistId":uploads, "maxResults":50}
        if cursor:
            opts["pageToken"]=cursor
        res = api.playlistItems().list(**opts).execute()
        items=res.get("items") or []
        ids=[x.get("contentDetails",{}).get("videoId") for x in items]
        if any(not x or not re.fullmatch(r"[-_a-zA-Z0-9]{11}",str(x)) for x in ids):
            raise RuntimeError("MALFORMED_CHANNEL_INVENTORY")
        if ids:
            details=api.videos().list(part="snippet,status",id=",".join(ids)).execute().get("items",[])
            if {x.get("id") for x in details}!=set(ids):
                raise RuntimeError("INCOMPLETE_CHANNEL_STATUS_REVIEW")
            for v in details:
                yield v
        cursor=res.get("nextPageToken")
        if not cursor:
            return
    raise RuntimeError("CHANNEL_INVENTORY_TOO_LONG_TO_SAFELY_CHECK_CANARY")


def verify_video(api, video_id):
    results=api.videos().list(part="id,status,snippet,processingDetails",id=video_id).execute().get("items",[])
    if len(results)!=1 or results[0].get("id")!=video_id:
        raise RuntimeError("CANARY_YOUTUBE_VIDEO_ID_NOT_READABLE")
    item=results[0]
    snippet=item.get("snippet") or {}
    status=item.get("status") or {}
    if status.get("privacyStatus")!="private":
        raise RuntimeError("CANARY_NOT_PRIVATE_STOP_ALL_PUBLICATION")
    if snippet.get("title")!=TITLE:
        raise RuntimeError("CANARY_METADATA_MISMATCH")
    if status.get("publishAt"):
        raise RuntimeError("CANARY_MUST_NEVER_BE_SCHEDULED")
    return {"id":video_id,
            "youtube_url":"https://www.youtube.com/watch?v="+video_id,
            "privacyStatus":status.get("privacyStatus"),
            "uploadStatus":status.get("uploadStatus"),
            "processingStatus":(item.get("processingDetails") or {}).get("processingStatus"),
            "confirmed_private":True,"scheduled":False}


def main():
    if os.environ.get("GITHUB_REPOSITORY")!=REPO:
        raise RuntimeError("WRONG_GITHUB_REPOSITORY")
    if os.environ.get("YOUTUBE_EXPECTED_CHANNEL_ID")!=CHANNEL:
        raise RuntimeError("WRONG_PINNED_CHANNEL")
    if os.environ.get("CANARY_CONFIRMATION")!=CONFIRM:
        raise RuntimeError("NO_EXPLICIT_PRIVATE_CANARY_CONFIRMATION")
    if os.environ.get("YOUTUBE_DIRECT_ENABLED","false").lower()=="true":
        raise RuntimeError("PRODUCTION_MODE_ENABLED_STOP_CANARY")
    video=Path("diagnostic-private-canary.mp4")
    if not video.is_file() or video.stat().st_size<30000:
        raise RuntimeError("DIAGNOSTIC_PRIVATE_MP4_MISSING")
    sha=hashlib.sha256(video.read_bytes()).hexdigest()
    api=authenticate()
    existing=[v for v in inventory(api)
              if v.get("snippet",{}).get("title")==TITLE]
    if len(existing)>1:
        raise RuntimeError("DUPLICATE_PRIVATE_CANARIES_FOUND_STOP")
    if existing:
        result=verify_video(api,existing[0]["id"])
        result["reused_existing"]=True
        print("EXISTING_PRIVATE_CANARY_REUSED", result["id"])
    else:
        from googleapiclient.http import MediaFileUpload
        body={
            "snippet":{
                "title":TITLE,
                "description":"INTEGRATION TEST ONLY. Generated original test pattern. Private forever; not production content.",
                "categoryId":"22",
                "tags":["gustava-api-test",TAG],
                "defaultLanguage":"ru",
            },
            "status":{
                "privacyStatus":"private",
                "selfDeclaredMadeForKids":False,
                "containsSyntheticMedia":False,
            },
        }
        request=api.videos().insert(
            part="snippet,status",body=body,
            media_body=MediaFileUpload(str(video),mimetype="video/mp4",chunksize=1024*1024,resumable=True),
            notifySubscribers=False)
        output=None
        while output is None:
            _,output=request.next_chunk()
        video_id=output.get("id")
        if not isinstance(video_id,str) or not re.fullmatch(r"[-_a-zA-Z0-9]{11}",video_id):
            raise RuntimeError("CANARY_UPLOAD_RETURNED_NO_YOUTUBE_ID_STOP_NO_RETRY")
        print("PRIVATE_CANARY_ACKNOWLEDGED", video_id, flush=True)
        result=None
        for _ in range(6):
            try:
                result=verify_video(api,video_id)
                break
            except RuntimeError as error:
                if str(error) in {"CANARY_NOT_PRIVATE_STOP_ALL_PUBLICATION",
                                  "CANARY_MUST_NEVER_BE_SCHEDULED",
                                  "CANARY_METADATA_MISMATCH"}:
                    raise
                time.sleep(3)
        if result is None:
            raise RuntimeError("CANARY_UPLOAD_UNCERTAIN_RECONCILE_BEFORE_RETRY")
        result["reused_existing"]=False
    result["sha256"]=sha
    result["test_only_not_approved_for_production"]=True
    Path("youtube-private-canary-receipt.json").write_text(
        json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
    print("PRIVATE_CANARY_VERIFIED",result["youtube_url"])
    print("LIVE_PUBLICATION_NOT_STARTED")
    return 0


if __name__=="__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # Don't print exception content from Google internals; could include request data.
        print("PRIVATE_CANARY_FAILED",type(exc).__name__, str(exc)[:150],file=sys.stderr)
        sys.exit(1)
