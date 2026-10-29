#!/usr/bin/env python3
"""One-shot action for first verified GUSTAVA Enduro Short: publish existing Buffer post now.

Never create a second Buffer post, reuse the existing post id and retain its media.
Run once only; no automatic retries when Buffer's action result is uncertain.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import json
import sys

from buffer_autopublish import buffer, verify_channel, CHANNEL

POST_ID = "6ae385c3b3aaeefe231f44cb"  # forest-corner-23, verified ledger receipt


def main():
    queue = verify_channel()  # Refuses a wrong, disconnected, or paused YouTube destination
    q = ('query { post(input:{id:"' + POST_ID +
         '"}) { id channelId status dueAt text assets { mimeType source } ' +
         'metadata { __typename ... on YoutubePostMetadata ' +
         '{ title category { categoryId } madeForKids isAiGenerated privacy } } } }')
    post = buffer(q).get("post") or {}
    if post.get("id") != POST_ID or post.get("channelId") != CHANNEL:
        raise RuntimeError("Priority post does not belong to the verified YouTube channel")
    if post.get("status") == "sent":
        print("ALREADY_SENT_ON_BUFFER", POST_ID)
        return
    if post.get("status") != "scheduled":
        raise RuntimeError("Not a scheduled YouTube post, refusing to force release")
    if POST_ID not in {p.get("id") for p in queue}:
        raise RuntimeError("Post is not in the verified scheduled Buffer queue")
    if not any(str(x.get("mimeType") or "").startswith("video/") for x in post.get("assets", [])):
        raise RuntimeError("Scheduled post is missing its video asset")
    due = datetime.fromisoformat(post["dueAt"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    if due <= now + timedelta(minutes=2):
        print("ALREADY_DUE_SOON: leave existing schedule intact", post["dueAt"])
        return
    # Buffer validates the FULL post on edit; an id+mode-only edit fails for YouTube.
    # Explicitly carry the exact original video, text and YouTube metadata forward.
    asset = post["assets"][0] if len(post["assets"]) == 1 else {}
    media_url = asset.get("source")
    if not media_url or "github.com/GUSTAVA009/moto-shorts-cloud/releases/download/gustava-forest-corner-23-" not in media_url:
        raise RuntimeError("Unexpected video source; refusing to replace media")
    yt = post.get("metadata") or {}
    title = yt.get("title")
    category = (yt.get("category") or {}).get("categoryId")
    if not title or not category or not post.get("text"):
        raise RuntimeError("Existing YouTube metadata incomplete; cannot safely edit")
    carried = {"id": POST_ID, "mode": "shareNow",
               "text": post["text"],
               "assets": [{"video": {"url": media_url}}],
               "metadata": {"youtube": {"title": title, "categoryId": category,
                   "madeForKids": bool(yt.get("madeForKids", False)),
                   "isAiGenerated": bool(yt.get("isAiGenerated", True)),
                   "privacy": "public"}}}
    mutation = """mutation($input:EditPostInput!){
      editPost(input:$input) {
        ... on PostActionSuccess { post { id channelId status dueAt } }
        ... on MutationError { message }
      }
    }"""
    result = buffer(mutation, {"input": carried}).get("editPost") or {}
    posted = result.get("post") or {}
    if result.get("message"):
        raise RuntimeError("Buffer refused shareNow: " + str(result["message"])[:180])
    if posted.get("id") != POST_ID or posted.get("channelId") != CHANNEL:
        raise RuntimeError("Buffer editPost result uncertain; never retry automatically")
    print("BUFFER_PRIORITY_RELEASE_REQUEST_ACCEPTED",
          json.dumps({"id": posted["id"], "status": posted.get("status"),
                      "dueAt": posted.get("dueAt")}, ensure_ascii=False))
    print("BUFFER_ACTION_ACCEPTED_NOT_YOUTUBE_DELIVERY_CONFIRMED")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("PRIORITY_RELEASE_NOT_CONFIRMED", type(exc).__name__, str(exc)[:180], file=sys.stderr)
        raise
