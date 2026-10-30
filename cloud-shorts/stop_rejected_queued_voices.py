#!/usr/bin/env python3
"""One-shot owner-selected voice change: no disliked narrator in FUTURE Shorts.

Only verified scheduled Buffer posts, exact known publication receipts, and
only a rendered old-voice episode are eligible. Sent/sending posts untouched.
Existing published YouTube videos, media releases and channel retained.
"""
import base64
from datetime import datetime,timezone,timedelta
import json
import os
from pathlib import Path
from buffer_autopublish import buffer, CHANNEL
import preview_queue as ledger

REPO="GUSTAVA009/moto-shorts-cloud"
TARGETS={
    "snow-trail-29":"6ae3965b18a6132aaf6ce3c3",
    "moto-forest-4bd53e13fec4":"6ae41ddba83a7fb63c94233c",
    "moto-motocross-a5697d86523a":"6ae425dea83a7fb63c95e988",
    "moto-repair-39610c24bde8":"6ae4271e56e01b976389aa6c",
}
CANCEL_STATE="cancelled_rejected_old_voice_owner_chose_deep"


def decode(entry):
    if not entry or not entry.get("sha") or not entry.get("content"):
        raise RuntimeError("Missing GitHub confirmation; not removing any post")
    return json.loads(base64.b64decode("".join(entry["content"].split()),validate=True))


def eligible(post,receipt,render_receipt,episode_id,expected_id,now):
    if receipt.get("episode") != episode_id or receipt.get("buffer_post_id") != expected_id:
        raise RuntimeError("Buffer publication receipt identity mismatch")
    if render_receipt.get("id") != episode_id:
        raise RuntimeError("Render provenance episode mismatch")
    if render_receipt.get("voice_profile") == "gustava_create_audio_deep_v1":
        return False
    if receipt.get("state") != "queued":
        return False
    if post.get("id") != expected_id or post.get("channelId") != CHANNEL:
        raise RuntimeError("Buffer post/channel identity mismatch")
    if post.get("status") != "scheduled":
        return False
    try:
        due=datetime.fromisoformat(post["dueAt"].replace("Z","+00:00"))
        logged=datetime.fromisoformat(receipt["due_at"].replace("Z","+00:00"))
    except (ValueError,TypeError,KeyError,AttributeError) as exc:
        raise RuntimeError("Untrusted scheduled time") from exc
    if due!=logged or due<=now+timedelta(minutes=2):
        return False
    return "deletePost" in (post.get("allowedActions") or [])


def cancel(fetch=buffer, read=ledger.api, save=ledger.store, now=None):
    if os.getenv("GITHUB_REPOSITORY") != REPO:
        raise RuntimeError("Wrong GitHub repository")
    now=now or datetime.now(timezone.utc)
    changed=[]
    skipped=[]
    for slug,expected in TARGETS.items():
        p="buffer-publication-receipts/"+slug+".json"
        recorded_entry=read(p)
        if not recorded_entry:
            skipped.append([slug,"no_receipt"])
            continue
        receipt=decode(recorded_entry)
        if receipt.get("state")==CANCEL_STATE:
            skipped.append([slug,"already_cancelled"])
            continue
        render_receipt=decode(read("render-receipts/"+slug+".json"))
        response=fetch('query { post(input:{id:"'+expected+
                       '"}) {id status channelId dueAt allowedActions} }')
        post=(response or {}).get("post") or {}
        if not post:
            skipped.append([slug,"post_not_visible"])
            continue
        if not eligible(post,receipt,render_receipt,slug,expected,now):
            skipped.append([slug,"no_longer_scheduled_or_action_unavailable"])
            continue
        output=fetch('mutation {deletePost(input:{id:"'+expected+
                    '"}) {... on DeletePostSuccess {id} ... on MutationError {message}} }')
        state=(output or {}).get("deletePost") or {}
        if state.get("id") != expected:
            raise RuntimeError("Buffer could not confirm cancellation of "+slug+
                               ": "+str(state.get("message","unknown"))[:160])
        receipt["state"]=CANCEL_STATE
        receipt["cancelled_reason"]="Owner rejected old narrator and approved AI Doc Maker deep only"
        save(p,receipt,"Remove future rejected narrator from Buffer "+slug,recorded_entry["sha"])
        changed.append([slug,expected])
        print("BUFFER_OLD_VOICE_SCHEDULED_POST_CANCELLED",slug,expected,flush=True)
    print("GUSTAVA_ONLY_DEEP_QUEUE_CLEANUP",
          json.dumps({"cancelled":changed,"skipped":skipped},ensure_ascii=False),
          flush=True)
    return changed


if __name__=="__main__":
    cancel()
