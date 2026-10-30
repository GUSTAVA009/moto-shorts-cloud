#!/usr/bin/env python3
"""Read-only reconciliation of historical GitHub Buffer receipts and live posts.

A GitHub receipt 'queued' means Buffer accepted scheduling, NOT YouTube sent.
Never delete, recreate, or repeat an uncertain post.
"""
from __future__ import annotations
import base64
import json
from pathlib import Path
from datetime import datetime, timezone

from buffer_autopublish import buffer, ORG, CHANNEL
from autofill_catalog import github
import preview_queue as ledger

def live_post_inventory(fetch=buffer):
    query = (
        'query { posts(first:100,input:{organizationId:"' + ORG +
        '",filter:{channelIds:["' + CHANNEL +
        '"]}}) {edges {node {id status dueAt sentAt}} '
        'pageInfo {hasNextPage}} }'
    )
    data = fetch(query).get("posts") or {}
    if (data.get("pageInfo") or {}).get("hasNextPage"):
        raise RuntimeError("BUFFER_POST_INVENTORY_TRUNCATED: refuse unverified comparisons")
    return [entry["node"] for entry in data.get("edges") or []]

def check_receipts(receipts, posts):
    inventory = {post["id"]: post for post in posts if post.get("id")}
    states = {}
    missing = []
    for r in receipts:
        post_id = r.get("buffer_post_id")
        if not post_id:
            continue
        row = inventory.get(post_id)
        if row is None:
            missing.append({"episode":r["episode"],"post_id":post_id,
                            "receipt_state":r.get("state"),"scheduled_due":r.get("due_at")})
        else:
            status = row.get("status")
            states[status] = states.get(status, 0) + 1
    return {
        "receipted_posts":sum(bool(r.get("buffer_post_id")) for r in receipts),
        "visible_posts":len(posts),
        "receipt_posts_by_buffer_status":states,
        "missing_receipted_posts":missing,
        "missing_count":len(missing),
        "note":"Missing from API does not prove deletion or success; no automatic retry is permitted."
    }

def main():
    tree = github("GET","git/trees/render-ledger?recursive=1")
    if tree.get("truncated"):
        raise RuntimeError("Render ledger tree truncated")
    paths=[x["path"] for x in tree.get("tree",[])
           if x["path"].startswith("buffer-publication-receipts/")
           and x["path"].endswith(".json")]
    receipts=[]
    for path in paths:
        entry=ledger.api(path)
        if not entry or not entry.get("content"):
            raise RuntimeError("Missing Buffer delivery receipt "+path)
        receipts.append(json.loads(base64.b64decode(
            "".join(entry["content"].split()),validate=True)))
    posts=live_post_inventory()
    result=check_receipts(receipts,posts)
    print("BUFFER_RECEIPT_RECONCILIATION",
          json.dumps(result,ensure_ascii=False),flush=True)
    if result["missing_count"]:
        print("::warning::BUFFER_POSTS_NOT_IN_LIVE_INVENTORY: "+str(result["missing_count"])+
              " accepted reservations not visible in active posts API; do not blindly resend",
              flush=True)
    failed=result["receipt_posts_by_buffer_status"].get("error",0)
    approval=result["receipt_posts_by_buffer_status"].get("needs_approval",0)
    if failed or approval:
        print("::warning::BUFFER_REVIEW_OR_DELIVERY_BLOCKERS error="+str(failed)+
              " needs_approval="+str(approval),flush=True)
    import os
    if os.getenv("GITHUB_STEP_SUMMARY"):
        content=["## Buffer receipts vs live YouTube publishing states",
                 "", "| Field | Value |", "|---|---|",
                 "| Confirmed Buffer scheduling receipts | "+str(result["receipted_posts"])+" |",
                 "| Matching posts absent from current Buffer response | "+str(result["missing_count"])+" |"]
        content += ["| Buffer "+str(k)+" | "+str(v)+" |"
                    for k,v in sorted(result["receipt_posts_by_buffer_status"].items())]
        content += ["", "A queued receipt is NOT evidence of successful YouTube publication."]
        Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text("\n".join(content)+"\n",encoding="utf8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
