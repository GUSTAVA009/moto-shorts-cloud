#!/usr/bin/env python3
"""Cancel exactly one demonstrably misleading future GUSTAVA Short.

The owner reviewed its actual MP4 and rejected helmet narration with NO
helmet in the stock footage. Do not delete a published post, other channel
posts, or posts whose IDs/time differ from the signed GitHub receipts.
"""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
import base64,json,os
from buffer_autopublish import buffer,CHANNEL
from autofill_catalog import github
from visual_director import verify_story_subject
import preview_queue as ledger

REPO="GUSTAVA009/moto-shorts-cloud"
SLUG="moto-helmet-f2452c64bf21"
EXPECTED_ID="6ae44d78ba1ca51fd300fbdd"
CANCELLED="cancelled_owner_rejected_visual_topic_mismatch"

def decode(entry):
    if not entry or not entry.get("content") or not entry.get("sha"):
        raise RuntimeError("No verified ledger. Do not touch Buffer")
    return json.loads(base64.b64decode("".join(entry["content"].split()),validate=True))

def visually_rejected(episode):
    try:
        verify_story_subject(episode)
    except ValueError as exc:
        if str(exc).startswith("VISUAL_TOPIC_MISMATCH"):
            return True
        raise
    return False

def may_cancel(post,receipt,episode,now):
    if not visually_rejected(episode):
        return False
    if (post.get("id") != EXPECTED_ID or receipt.get("buffer_post_id")!=EXPECTED_ID
            or receipt.get("episode")!=SLUG or receipt.get("state")!="queued"
            or post.get("channelId")!=CHANNEL or post.get("status")!="scheduled"):
        return False
    try:
        due=datetime.fromisoformat(post["dueAt"].replace("Z","+00:00"))
        recorded=datetime.fromisoformat(receipt["due_at"].replace("Z","+00:00"))
    except (ValueError,AttributeError,KeyError):
        return False
    return (due==recorded and due>now+timedelta(minutes=3)
            and "deletePost" in (post.get("allowedActions") or []))

def cancel(fetch=buffer,read=ledger.api,save=ledger.store,now=None):
    if os.environ.get("GITHUB_REPOSITORY")!=REPO:
        raise RuntimeError("Wrong repository")
    now=now or datetime.now(timezone.utc)
    entry=read("buffer-publication-receipts/"+SLUG+".json")
    if not entry:
        print("MISLEADING_HELMET_NO_RECEIPT")
        return False
    receipt=decode(entry)
    if receipt.get("state")==CANCELLED:
        print("MISLEADING_HELMET_ALREADY_CANCELLED")
        return False
    c=github("GET","contents/cloud-shorts/episodes.json?ref=main")
    catalog=json.loads(base64.b64decode("".join(c["content"].split())))
    ep=next((e for e in catalog["episodes"] if e["id"]==SLUG),None)
    if ep is None or not visually_rejected(ep):
        raise RuntimeError("Source visual problem no longer provable")
    response=fetch('query {post(input:{id:"'+EXPECTED_ID+
                   '"}) {id status channelId dueAt allowedActions}}')
    post=(response or {}).get("post") or {}
    if not may_cancel(post,receipt,ep,now):
        print("MISLEADING_HELMET_NOT_SCHEDULED_OR_NO_DELETE_PERMISSION")
        return False
    response=fetch('mutation {deletePost(input:{id:"'+EXPECTED_ID+
                   '"}) {... on DeletePostSuccess {id} ... on MutationError {message}}}')
    state=(response or {}).get("deletePost") or {}
    if state.get("id")!=EXPECTED_ID:
        raise RuntimeError("Buffer did not confirm exact post cancellation")
    receipt["state"]=CANCELLED
    receipt["cancelled_reason"]="Owner reviewed MP4: no helmet, confusing A/B/A/B visuals"
    save("buffer-publication-receipts/"+SLUG+".json",receipt,
         "Cancel rejected helmet Short: topic not shown in footage",entry["sha"])
    print("MISLEADING_HELMET_CANCELLED_CONFIRMED",SLUG,EXPECTED_ID,flush=True)
    return True

if __name__=="__main__":
    cancel()
