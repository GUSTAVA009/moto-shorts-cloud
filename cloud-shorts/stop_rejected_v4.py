#!/usr/bin/env python3
"""One-shot owner-requested halt of rejected v4 voice, exact scheduled post only.

Never touch sent/unknown posts, other posts, or a different channel. The old
deduplication receipt remains after the scheduled post is cancelled.
"""
from __future__ import annotations
import os, json
from datetime import datetime,timezone
from buffer_autopublish import buffer, CHANNEL
import preview_queue as ledger

EPISODE="jump-track-28"
POST_ID="6ae401186385db216a1e42db"
OLD_VOICE="gustava_male_natural_v4"

def cancel(fetch=buffer, lookup=ledger.api, save=ledger.store):
    if os.getenv("GITHUB_REPOSITORY") != "GUSTAVA009/moto-shorts-cloud":
        raise RuntimeError("Wrong repository: cannot cancel a post")
    path="buffer-publication-receipts/"+EPISODE+".json"
    entry=lookup(path)
    if not entry or not entry.get("sha") or not entry.get("content"):
        raise RuntimeError("Missing exact Buffer reservation")
    import base64
    receipt=json.loads(base64.b64decode("".join(entry["content"].split()),validate=True))
    if receipt.get("episode") != EPISODE or receipt.get("buffer_post_id") != POST_ID:
        raise RuntimeError("Buffer receipt mismatch: no cancellation")
    if receipt.get("state") == "cancelled_rejected_v4":
        print("BUFFER_REJECTED_V4_ALREADY_CANCELLED",flush=True)
        return "already_cancelled"
    if receipt.get("state") != "queued":
        raise RuntimeError("Buffer reservation not in queued state")
    rend=lookup("render-receipts/"+EPISODE+".json")
    if not rend or not rend.get("content"):
        raise RuntimeError("Missing render receipt for rejected narrator")
    job=json.loads(base64.b64decode("".join(rend["content"].split()),validate=True))
    if job.get("voice_profile") != OLD_VOICE or job.get("run_id") != "40991345752":
        raise RuntimeError("Render identity/voice is not the rejected v4; refusing cancellation")
    raw=fetch('query { post(input:{id:"'+POST_ID+'"}) {id status channelId dueAt allowedActions} }')
    post=raw.get("post") or {}
    if post.get("id") != POST_ID or post.get("channelId") != CHANNEL:
        raise RuntimeError("Post identity/channel not confirmed")
    if post.get("status") != "scheduled":
        print("REJECTED_V4_NOT_SCHEDULED",str(post.get("status")),flush=True)
        return "not_scheduled"
    allowed=post.get("allowedActions") or []
    if "deletePost" not in allowed:
        print("REJECTED_V4_MANUAL_CANCEL_REQUIRED: Buffer deletePost action unavailable")
        return "not_deletable"
    due=datetime.fromisoformat(post["dueAt"].replace("Z","+00:00"))
    if due <= datetime.now(timezone.utc):
        print("REJECTED_V4_DUE_ALREADY_REACHED: no unsafe delete")
        return "already_due"
    result=fetch('mutation {deletePost(input:{id:"'+POST_ID+
                 '"}) {... on DeletePostSuccess {id} ... on MutationError {message}} }')
    state=result.get("deletePost") or {}
    if state.get("id") != POST_ID:
        raise RuntimeError("Buffer did not confirm exact post cancellation: "+
                           str(state.get("message","unknown"))[:140])
    receipt["state"]="cancelled_rejected_v4"
    receipt["cancelled_reason"]="Owner explicitly rejected synthetic v4 voice; wait for new baritone profile"
    save(path,receipt,"Cancel scheduled rejected-v4 narration: "+EPISODE,entry["sha"])
    print("REJECTED_V4_SCHEDULED_POST_CANCELLED",EPISODE,POST_ID,flush=True)
    return "cancelled"

if __name__=="__main__":
    cancel()
