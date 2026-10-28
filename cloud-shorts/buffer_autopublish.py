#!/usr/bin/env python3
"""Queue one verified Shorts artifact via Cloudflare R2 + Buffer (no own server)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

import publora_autopublish as prior
import preview_queue as ledger

MUTATION = """mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess { post { id dueAt } }
    ... on MutationError { message }
  }
}"""
CHANNEL = "UCS0QCodPcFBTjMt4ioEWOUw"

def required(name):
    v = os.environ.get(name, "").strip()
    if not v:
        raise RuntimeError("Missing configuration: " + name)
    return v

def validate(ep, meta, voice, mixed, video):
    qa = dict(voice, mixed_audio=mixed)
    prior.publication_allowed(ep, meta, qa, video)
    if min(float(voice.get("lexical_coverage", 0)), float(mixed.get("lexical_coverage", 0))) < .95:
        raise ValueError("Narration accuracy below 95%; publishing blocked")
    if required("YOUTUBE_EXPECTED_CHANNEL_ID") != CHANNEL:
        raise ValueError("Wrong destination YouTube channel")
    return prior.file_sha256(video)

def public_url(sha):
    base = required("R2_PUBLIC_BASE_URL").rstrip("/")
    if not re.fullmatch(r"https://[a-zA-Z0-9.-]+(?:/[a-zA-Z0-9/_-]+)?", base):
        raise ValueError("Expected stable HTTPS public R2 URL, without query parameters")
    if ".r2.cloudflarestorage.com" in base:
        raise ValueError("R2 storage endpoint is not a public media URL")
    return base + "/gustava-shorts/" + sha + ".mp4"

def upload_r2(video, sha):
    import boto3
    endpoint = required("R2_ENDPOINT")
    if not re.fullmatch(r"https://[a-f0-9]{32}\.r2\.cloudflarestorage\.com", endpoint):
        raise ValueError("Invalid Cloudflare R2 endpoint")
    client = boto3.client("s3", region_name="auto", endpoint_url=endpoint,
        aws_access_key_id=required("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=required("R2_SECRET_ACCESS_KEY"))
    client.upload_file(str(video), required("R2_BUCKET"),
        "gustava-shorts/" + sha + ".mp4", ExtraArgs={"ContentType":"video/mp4"})
    url = public_url(sha)
    req = urllib.request.Request(url, method="HEAD",
        headers={"User-Agent":"GUSTAVA-Shorts/1.0"})
    with urllib.request.urlopen(req, timeout=35) as r:
        if r.status != 200 or "video/" not in r.headers.get("Content-Type",""):
            raise RuntimeError("MP4 is not accessible at permanent public HTTPS URL")
    return url

def buffer_post(title, description, media_url):
    channel_id = required("BUFFER_CHANNEL_ID")
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,100}", channel_id):
        raise ValueError("Invalid Buffer channel ID")
    payload = {"query": MUTATION, "variables": {"input": {
        "channelId": channel_id, "text": title.strip() + "\n\n" + description.strip(),
        "schedulingType":"automatic", "mode":"addToQueue",
        "assets":[{"video":{"url":media_url}}]
    }}}
    req = urllib.request.Request("https://api.buffer.com",
        data=json.dumps(payload,ensure_ascii=False).encode("utf8"), method="POST",
        headers={"Content-Type":"application/json",
                 "Authorization":"Bearer "+required("BUFFER_API_KEY")})
    try:
        with urllib.request.urlopen(req,timeout=45) as response:
            data=json.load(response)
    except urllib.error.HTTPError as ex:
        raise RuntimeError("Buffer request returned HTTP "+str(ex.code)) from None
    if data.get("errors"):
        raise RuntimeError("Buffer GraphQL error; reconcile before retry")
    result=(data.get("data") or {}).get("createPost") or {}
    if result.get("message") or not (result.get("post") or {}).get("id"):
        raise RuntimeError("Buffer queue outcome unknown; reconcile before retry")
    return result["post"]

def deliver(ep, meta, voice, mixed, video, dry_run=False):
    sha = validate(ep, meta, voice, mixed, video)
    receipt_path = prior.receipt_path(ep["id"])
    if dry_run:
        return {"dry_run":True, "episode":ep["id"],"sha256":sha}
    if os.getenv("BUFFER_AUTO_PUBLISH_ENABLED","").lower() != "true":
        return {"skipped":"BUFFER_AUTO_PUBLISH_ENABLED not true"}
    for key in ("BUFFER_API_KEY","BUFFER_CHANNEL_ID","R2_ENDPOINT","R2_ACCESS_KEY_ID",
                "R2_SECRET_ACCESS_KEY","R2_BUCKET","R2_PUBLIC_BASE_URL"):
        required(key)
    public_url(sha)
    if ledger.api(receipt_path) is not None:
        return {"skipped":"Existing Publora/Buffer publication receipt; do not duplicate"}
    receipt={"episode":ep["id"],"sha256":sha,"provider":"buffer",
             "state":"reserved","run_id":os.getenv("GITHUB_RUN_ID",""),
             "warning":"No automatic retry after an uncertain result"}
    prior.record(receipt_path,receipt)
    # IMPORTANT: reserve before first external side effect; fail-closed.
    media_url=upload_r2(video,sha)
    receipt.update(state="media_ready",media_url=media_url)
    prior.update(receipt_path,receipt)
    receipt["state"]="queue_requested"
    prior.update(receipt_path,receipt)
    post=buffer_post(meta["title"],meta["description"],media_url)
    receipt.update(state="queued",buffer_post_id=post["id"],due_at=post.get("dueAt"))
    prior.update(receipt_path,receipt)
    return {"queued":True,"episode":ep["id"],"buffer_post_id":post["id"],
            "due_at":post.get("dueAt")}

def main():
    p=argparse.ArgumentParser()
    for name in ("video","metadata","voice-qa","mixed-qa","catalog"):
        p.add_argument("--"+name,type=Path,required=name!="catalog")
    p.add_argument("--episode",required=True)
    p.add_argument("--dry-run",action="store_true")
    a=p.parse_args()
    catalog=json.loads((a.catalog or Path(__file__).with_name("episodes.json")).read_text(encoding="utf8"))
    ep=next((e for e in catalog["episodes"] if e["id"]==a.episode),None)
    if ep is None:
        raise ValueError("Unknown episode")
    obj=lambda p:json.loads(p.read_text(encoding="utf8"))
    print("BUFFER_DELIVERY",json.dumps(deliver(ep,obj(a.metadata),obj(a.voice_qa),obj(a.mixed_qa),
                                         a.video,a.dry_run),ensure_ascii=False))

if __name__=="__main__":
    try:main()
    except Exception as ex:
        print("BUFFER_BLOCKED",str(ex),file=sys.stderr)
        sys.exit(1)
