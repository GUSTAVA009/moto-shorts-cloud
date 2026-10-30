#!/usr/bin/env python3
"""Correct accidentally enabled YouTube GenAI disclosures in scheduled Buffer posts.

Scope: our OWN verified real-stock motorcycle Shorts only, and ONLY a post
whose ledger has the exact confirmed Buffer ID. This does not modify any
YouTube-generated or compulsory platform label, nor any sent/unknown post.

The original 'aiAssisted' authoring fact remains untouched. The YouTube
'isAiGenerated' disclosure was erroneously forced on for these verified
non-photorealistically-generated stock footage videos.
"""
from __future__ import annotations
import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

from autofill_catalog import github
from buffer_autopublish import buffer, ORG, CHANNEL, should_disclose_generated_content
from channel_focus import is_motorcycle_episode
import preview_queue as ledger

REPO = "GUSTAVA009/moto-shorts-cloud"

POST_FIELDS = (
    "id channelId status dueAt text "
    "assets {id type source} "
    "metadata {... on YoutubePostMetadata {"
    "isAiGenerated title category {categoryId} "
    "madeForKids privacy license embeddable notifySubscribers}}"
)


def live_inventory(fetch=buffer):
    query = (
        'query { posts(first:100,input:{organizationId:"'+ORG+
        '",filter:{status:[scheduled],channelIds:["'+CHANNEL+
        '"]}}) {edges{node{'+POST_FIELDS+
        '}} pageInfo{hasNextPage}}}'
    )
    data = (fetch(query) or {}).get("posts") or {}
    if (data.get("pageInfo") or {}).get("hasNextPage") is not False:
        raise RuntimeError("Buffer inventory incomplete; no edits permitted")
    return [e["node"] for e in data.get("edges") or []]


def read_ledger_file(path, read=ledger.api):
    entry = read(path)
    if not entry or not entry.get("content"):
        raise RuntimeError("Missing publishing receipt: " + path)
    try:
        return json.loads(base64.b64decode(
            "".join(entry["content"].split()), validate=True))
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Corrupt publishing receipt: " + path) from exc


def eligible(post, receipt, episode, now):
    if not isinstance(post, dict) or not isinstance(receipt, dict):
        return False
    if post.get("id") != receipt.get("buffer_post_id"):
        return False
    if (receipt.get("state") != "queued" or
            receipt.get("episode") != episode.get("id")):
        return False
    if post.get("channelId") != CHANNEL or post.get("status") != "scheduled":
        return False
    youtube = post.get("metadata") or {}
    if youtube.get("isAiGenerated") is not True:
        return False
    if not is_motorcycle_episode(episode):
        return False
    if should_disclose_generated_content(episode):
        return False
    if not episode.get("auto_publish") is True:
        return False
    try:
        due = datetime.fromisoformat(post["dueAt"].replace("Z", "+00:00"))
        recorded = datetime.fromisoformat(receipt["due_at"].replace("Z", "+00:00"))
        if due.tzinfo is None or recorded.tzinfo is None:
            return False
        if due != recorded or due <= now + timedelta(minutes=2):
            return False
    except (ValueError, TypeError, KeyError, AttributeError):
        return False
    return True


def patch_ai_disclosure(post, fetch=buffer):
    """Edit one post without changing its contents or schedule.

    Buffer validates the *entire* post on an edit. Live API rejected a
    metadata-only mutation as 'missing text, media, title' in run 41009770736,
    despite documentation saying omission should preserve those fields.
    Carry forward those same fields from live POST data, verifying every bit.
    """
    metadata = post.get("metadata") or {}
    original_assets = post.get("assets") or []
    category = (metadata.get("category") or {}).get("categoryId")
    if not (post.get("text") and metadata.get("title") and category in (
        "1","2","10","15","17","19","20","22","23","24","25","26","27","28","29")):
        raise RuntimeError("Incomplete YouTube text/title/category; no mutation allowed")
    if len(original_assets) != 1:
        raise RuntimeError("Unexpected multiple/missing video assets; no mutation allowed")
    video = original_assets[0]
    source = video.get("source")
    if video.get("type") != "video" or not isinstance(source, str) or not source.startswith("https://"):
        raise RuntimeError("Live video asset source invalid; no mutation allowed")
    youtube = {
        "isAiGenerated": False,
        "title": metadata["title"],
        "categoryId": category,
    }
    for key in ("madeForKids","privacy","license","embeddable","notifySubscribers"):
        if metadata.get(key) is not None:
            youtube[key] = metadata[key]
    payload = {
        "id": post["id"], "text": post["text"],
        "assets": [{"video":{"url":source}}],
        "metadata": {"youtube": youtube},
    }
    query = (
        "mutation($input:EditPostInput!){editPost(input:$input){"
        "... on PostActionSuccess{post{"+POST_FIELDS+"}}"
        "... on MutationError{message}"
        "}}"
    )
    result = (fetch(query, {"input": payload}) or {}).get("editPost") or {}
    after = result.get("post")
    if not isinstance(after, dict):
        raise RuntimeError("Buffer edit rejected or uncertain: "+str(result.get("message","unknown"))[:600])
    for key in ("id","channelId","status","dueAt","text"):
        if after.get(key) != post.get(key):
            raise RuntimeError("Buffer edit unexpectedly changed "+key+"; audit required")
    got_assets = after.get("assets") or []
    if len(got_assets) != 1 or got_assets[0].get("source") != source or got_assets[0].get("type") != "video":
        raise RuntimeError("Buffer edit unexpectedly changed video source; audit required")
    actual_meta = after.get("metadata") or {}
    if actual_meta.get("isAiGenerated") is not False:
        raise RuntimeError("Buffer did not confirm false AI-generated marker")
    for key in ("title","category","madeForKids","privacy","license","embeddable","notifySubscribers"):
        if actual_meta.get(key) != metadata.get(key):
            raise RuntimeError("Buffer edit unexpectedly changed Youtube metadata."+key)
    return after


def run():
    if os.getenv("GITHUB_REPOSITORY") != REPO:
        raise RuntimeError("Wrong repository; no Buffer edits allowed")
    catalog_entry = github("GET", "contents/cloud-shorts/episodes.json?ref=main")
    catalog = json.loads(base64.b64decode(
        "".join(catalog_entry["content"].split()), validate=True))
    by_id={e["id"]:e for e in catalog["episodes"]}
    tree = github("GET","git/trees/render-ledger?recursive=1")
    if tree.get("truncated"):
        raise RuntimeError("Incomplete ledger; refusing edits")
    receipts={}
    for row in tree.get("tree") or []:
        path=row.get("path","")
        if path.startswith("buffer-publication-receipts/") and path.endswith(".json"):
            doc=read_ledger_file(path)
            if doc.get("buffer_post_id"):
                receipts[doc["buffer_post_id"]]=doc
    scheduled=live_inventory()
    changed=[]
    ignored=[]
    now=datetime.now(timezone.utc)
    for post in scheduled:
        receipt=receipts.get(post.get("id"))
        ep=by_id.get((receipt or {}).get("episode"))
        if not ep or not eligible(post, receipt, ep, now):
            ignored.append(post.get("id"))
            continue
        result=patch_ai_disclosure(post)
        changed.append({"episode":ep["id"],"post_id":result["id"],
                        "still_scheduled":result["dueAt"]})
        print("BUFFER_UNNEEDED_AI_LABEL_CORRECTED",ep["id"],result["id"],flush=True)
    print("BUFFER_AI_DISCLOSURE_AUDIT",json.dumps({
        "changed":changed,"skipped":len(ignored),
        "scheduled_examined":len(scheduled),
        "scope":"only owned queued stock-video posts; true AI disclosure always preserved",
    },ensure_ascii=False),flush=True)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text(
            "## Correct accidental AI-generated Shorts flag\n\n"
            +f"- Scheduled posts checked: {len(scheduled)}\n"
            +f"- Corrected eligible posts: {len(changed)}\n"
            +f"- Unchanged/unknown/disclosure-required: {len(ignored)}\n\n"
            +"No post, media, title, date or AI assistance provenance was removed.\n",
            encoding="utf8")
    return 0


if __name__=="__main__":
    raise SystemExit(run())
