#!/usr/bin/env python3
"""Read-only Buffer API readiness: verify exact connected YouTube channel and queue.
Safe to run as the very first authenticated API call. Never publishes or edits.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

from buffer_autopublish import BUFFER_CHANNEL

BASE = "https://api.buffer.com"
ORG_RE = re.compile(r"^[a-f0-9]{24}$")

def request(query):
    key = os.environ.get("BUFFER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("BUFFER_API_KEY is not configured in Actions secrets")
    req = urllib.request.Request(BASE, data=json.dumps({"query":query}).encode("utf8"),
        method="POST", headers={"Content-Type":"application/json",
                                "Authorization":"Bearer "+key,
                                "User-Agent":"GUSTAVA-Shorts-Readiness/1.0"})
    try:
        with urllib.request.urlopen(req,timeout=28) as response:
            data=json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("Buffer API refused read-only query, HTTP "+str(exc.code)) from None
    if not isinstance(data,dict) or data.get("errors"):
        raise RuntimeError("Buffer API GraphQL query failed; no scheduling allowed")
    return data.get("data") or {}

def inspect():
    root = request("query { account { organizations { id name } } }")
    organizations=(root.get("account") or {}).get("organizations") or []
    if not isinstance(organizations,list) or not organizations:
        raise RuntimeError("Buffer account returned no organizations")
    for org in organizations:
        org_id = org.get("id","")
        if not isinstance(org_id,str) or not ORG_RE.fullmatch(org_id):
            raise RuntimeError("Invalid Buffer organization ID")
        query = 'query { channels(input: { organizationId: "'+org_id+'" }) { id name service organizationId isDisconnected isLocked isQueuePaused } }'
        channels=request(query).get("channels") or []
        for channel in channels:
            if channel.get("id") != BUFFER_CHANNEL:
                continue
            if str(channel.get("service","")).lower() != "youtube":
                raise RuntimeError("Wrong network on verified Buffer channel")
            for flag in ("isDisconnected","isLocked","isQueuePaused"):
                if channel.get(flag) is True:
                    raise RuntimeError("YouTube channel is not ready: "+flag)
            q='query { posts(first: 11, input: { organizationId: "'+org_id+'", filter: { status: [scheduled], channelIds: ["'+BUFFER_CHANNEL+'"] } }) { edges { node { id } } pageInfo { hasNextPage } } }'
            queued=request(q).get("posts") or {}
            if not isinstance(queued.get("edges"),list):
                raise RuntimeError("Buffer scheduled-post queue could not be checked")
            count=len(queued["edges"])
            return {"connected":True,"channel_name":channel.get("name"),
                    "buffer_channel_id":BUFFER_CHANNEL,
                    "organization_id":org_id,
                    "queued_at_least":count,
                    "queue_capacity":10,
                    "queue_has_room":count<10 and not (queued.get("pageInfo") or {}).get("hasNextPage",False)}
    raise RuntimeError("GUSTAVA Enduro not found among Buffer account channels")

def main():
    info=inspect()
    print("BUFFER_READINESS",json.dumps(info,ensure_ascii=False))
    if not info["queue_has_room"]:
        print("BUFFER_QUEUE_FULL: let a previously queued Short publish before scheduling another.")
    return 0

if __name__ == "__main__":
    try:sys.exit(main())
    except Exception as exc:
        print("BUFFER_NOT_READY",str(exc),file=sys.stderr)
        sys.exit(1)
