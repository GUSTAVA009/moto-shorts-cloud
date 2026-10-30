#!/usr/bin/env python3
"""Publish one reviewed Shorts MP4 into the configured Buffer YouTube queue.

GitHub Actions needs BUFFER_API_KEY, GITHUB_TOKEN, GITHUB_REPOSITORY and
BUFFER_AUTO_PUBLISH_ENABLED=true. Existing historical/Buffer receipts prevent
duplicate submissions. An uncertain Buffer response never triggers a retry.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

import preview_queue as ledger
from publication_safety import publication_allowed, file_sha256
from channel_focus import is_motorcycle_episode
from ten_daily_slots import choose_slot

CHANNEL = "6ae238b32f1f5ed648ff9011"
ORG = "6ae237b760e9c8dd49173dc8"
YOUTUBE = "UCS0QCodPcFBTjMt4ioEWOUw"


def buffer(query, variables=None):
    key = os.getenv("BUFFER_API_KEY", "")
    if len(key) < 30:
        raise RuntimeError("Buffer API key missing")
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request("https://api.buffer.com", data=body, method="POST",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("Buffer HTTP " + str(exc.code)) from None
    if data.get("errors"):
        raise RuntimeError("Buffer GraphQL request rejected")
    return data.get("data") or {}


def verify_channel(include_sent=False, include_errors=False):
    """Verify pinned YouTube destination, queue and recent sent posts in ONE API call."""
    if os.getenv("YOUTUBE_EXPECTED_CHANNEL_ID", YOUTUBE) != YOUTUBE:
        raise RuntimeError("Expected YouTube channel does not match Buffer channel")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat().replace("+00:00", "Z")
    q = ('query { channel(input:{id:"' + CHANNEL +
         '"}) {id name service serviceId isQueuePaused isDisconnected} '
         'scheduledPosts: posts(first:100,input:{organizationId:"' + ORG +
         '",filter:{status:[scheduled],channelIds:["' + CHANNEL +
         '"]}}) {edges {node {id text dueAt}} pageInfo {hasNextPage}} '
         'sentPosts: posts(first:100,input:{organizationId:"' + ORG +
         '",filter:{status:[sent],channelIds:["' + CHANNEL +
         '"],dueAt:{start:"' + cutoff +
         '"}}}) {edges {node {id dueAt sentAt}} pageInfo {hasNextPage}} }')
    if include_errors:
        # Read-only diagnostics: a missing YouTube publication can be in
        # Buffer's documented 'error' or still-'sending' status rather
        # than either 'scheduled' or 'sent'.
        extra = (
            ' errorPosts: posts(first:100,input:{organizationId:"' + ORG +
            '",filter:{status:[error],channelIds:["' + CHANNEL +
            '"],dueAt:{start:"' + cutoff +
            '"}}}) {edges {node {id status dueAt}} pageInfo {hasNextPage}}'
            ' sendingPosts: posts(first:100,input:{organizationId:"' + ORG +
            '",filter:{status:[sending],channelIds:["' + CHANNEL +
            '"],dueAt:{start:"' + cutoff +
            '"}}}) {edges {node {id status dueAt}} pageInfo {hasNextPage}}'
        )
        q = q.rsplit("}", 1)[0] + extra + " }"
    data = buffer(q)
    channel = data.get("channel") or {}
    if (channel.get("id") != CHANNEL or channel.get("service") != "youtube" or
            channel.get("serviceId") != YOUTUBE or
            channel.get("isQueuePaused") is not False or
            channel.get("isDisconnected") is not False):
        raise RuntimeError("Incorrect or unavailable YouTube channel")
    scheduled = data.get("scheduledPosts") or {}
    sent = data.get("sentPosts") or {}
    if ((scheduled.get("pageInfo") or {}).get("hasNextPage") or
            (sent.get("pageInfo") or {}).get("hasNextPage")):
        raise RuntimeError("Buffer inventory incomplete; cannot risk exceeding posting limits")
    posts = [x["node"] for x in scheduled.get("edges") or []]
    sent_posts = [x["node"] for x in sent.get("edges") or []]
    if include_errors:
        errors = data.get("errorPosts") or {}
        sending = data.get("sendingPosts") or {}
        if ((errors.get("pageInfo") or {}).get("hasNextPage") or
                (sending.get("pageInfo") or {}).get("hasNextPage")):
            raise RuntimeError("Buffer error/sending history incomplete; no false delivery status")
        error_posts = [x["node"] for x in errors.get("edges") or []]
        sending_posts = [x["node"] for x in sending.get("edges") or []]
        if include_sent:
            return posts, sent_posts, error_posts, sending_posts
        return posts, error_posts, sending_posts
    return (posts, sent_posts) if include_sent else posts


def recently_sent():
    """Count posts already published today against the ten-per-day target."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat().replace("+00:00", "Z")
    q = ('query {posts(first:100,input:{organizationId:"' + ORG +
         '",filter:{status:[sent],channelIds:["' + CHANNEL +
         '"],dueAt:{start:"' + cutoff +
         '"}}}) {edges {node {id dueAt}} pageInfo {hasNextPage}}}')
    data = buffer(q).get("posts") or {}
    if (data.get("pageInfo") or {}).get("hasNextPage"):
        raise RuntimeError("Recent sent-post inventory incomplete; refuse an extra upload")
    return [x["node"] for x in data.get("edges", [])]


def validate_video(video):
    p = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
        "format=duration:stream=codec_type,width,height,duration,nb_read_frames,avg_frame_rate,channels",
        "-of", "json", str(video)], capture_output=True, text=True, timeout=55, check=True)
    data = json.loads(p.stdout)
    v = next((x for x in data.get("streams", []) if x.get("codec_type") == "video"), {})
    a = next((x for x in data.get("streams", []) if x.get("codec_type") == "audio"), {})
    seconds = float(data.get("format", {}).get("duration") or 0)
    rate = v.get("avg_frame_rate", "0/1").split("/")
    fps = float(rate[0]) / max(1.0, float(rate[1]))
    frames = int(v.get("nb_read_frames") or 0)
    if (not 7 <= seconds <= 180 or not a or int(a.get('channels') or 0) != 2 or
        v.get("width", 0) >= v.get("height", 0) or
        fps < 23.9 or frames < seconds * fps * .96 or
        abs(float(v.get("duration") or 0) - seconds) > .5):
        raise RuntimeError("MP4 length, centered stereo narration/music, vertical frame or codec QA failed")
    frozen = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-an",
        "-vf", "freezedetect=n=-45dB:d=2.2", "-f", "null", "-"],
        capture_output=True, text=True, timeout=100, check=True)
    if "freeze_start:" in frozen.stderr:
        raise RuntimeError("MP4 frozen footage detected")


def release_url(episode, video, sha):
    repo = os.environ["GITHUB_REPOSITORY"]
    if repo != "GUSTAVA009/moto-shorts-cloud":
        raise RuntimeError("Wrong GitHub repository")
    tag = "gustava-" + episode + "-" + sha[:12]
    name = episode + ".mp4"
    env = dict(os.environ, GH_TOKEN=os.environ["GITHUB_TOKEN"],
               GH_REPO=repo)
    def gh(*args):
        return subprocess.run(["gh", *args], env=env, capture_output=True,
                              text=True, timeout=150)
    found = gh("release", "view", tag, "--json", "assets")
    if found.returncode == 0:
        assets = json.loads(found.stdout).get("assets", [])
        asset = next((x for x in assets if x.get("name") == name), None)
        if not asset or asset.get("size") != video.stat().st_size:
            raise RuntimeError("Existing release media mismatches new MP4")
        if asset.get("digest") and asset["digest"] != "sha256:" + sha:
            raise RuntimeError("Existing release checksum mismatch")
    else:
        result = gh("release", "create", tag, str(video),
                    "--title", "GUSTAVA " + episode, "--notes",
                    "Reviewed original Shorts video for Buffer distribution.",
                    "--latest=false")
        if result.returncode:
            raise RuntimeError("Could not securely store MP4 as GitHub Release")
    url = ("https://github.com/" + repo + "/releases/download/" +
           tag + "/" + name)
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=40) as response:
        if response.status != 200:
            raise RuntimeError("GitHub media URL is unavailable")
    return url


def publish(episode, video, metadata, voice, mixed):
    if os.getenv("BUFFER_AUTO_PUBLISH_ENABLED") != "true":
        return {"skipped": "Buffer auto-publication disabled"}
    if not is_motorcycle_episode(episode):
        return {"skipped": "CHANNEL_TOPIC_BLOCKED: episode is unrelated to GUSTAVA Enduro"}
    if episode.get("auto_publish") is not True or episode.get("voice_engine") != "kokoro_ru_dima":
        return {"skipped": "Episode or narrator not approved for automatic publication"}
    rec = "buffer-publication-receipts/" + episode["id"] + ".json"
    if ledger.api(rec) or ledger.api("publication-receipts/" + episode["id"] + ".json"):
        return {"skipped": "Publication already reserved or submitted"}
    voice["mixed_audio"] = mixed
    publication_allowed(episode, metadata, voice, video)
    validate_video(video)
    posts, sent_posts = verify_channel(include_sent=True)
    if len(posts) >= 10:
        return {"skipped": "Buffer queue near capacity (10 queued, Free plan maximum); retry after the next publication"}
    if any(p.get("text", "").strip() == metadata["description"].strip() for p in posts):
        raise RuntimeError("Potential identical scheduled post in Buffer")
    due_at = choose_slot(posts + sent_posts,
                         timezone_name=os.getenv("GUSTAVA_POST_TIMEZONE", "Europe/Moscow"))
    sha = file_sha256(video)
    url = release_url(episode["id"], video, sha)
    state = {"episode": episode["id"], "sha256": sha, "media_url": url,
             "state": "reserved", "warning": "Never retry unknown Buffer createPost"}
    ledger.store(rec, state, "Reserve Buffer delivery for " + episode["id"])
    title = metadata["title"][:100]
    desc = metadata["description"]
    category = "2" if re.search(r"мото|байк|гонк", title + " " + desc, re.I) else "28"
    payload = {
        "channelId": CHANNEL, "text": desc, "schedulingType": "automatic",
        "mode": "customScheduled", "dueAt": due_at, "aiAssisted": True,
        "metadata": {"youtube": {"title": title, "categoryId": category,
                     "madeForKids": False, "privacy": "public",
                     "isAiGenerated": True}},
        "assets": [{"video": {"url": url}}]
    }
    q = """mutation($input:CreatePostInput!){
      createPost(input:$input) {
        ... on PostActionSuccess {post {id channelId dueAt status}}
        ... on MutationError {message}
      }
    }"""
    response = buffer(q, {"input": payload}).get("createPost") or {}
    post = response.get("post")
    if not post or post.get("channelId") != CHANNEL:
        raise RuntimeError("Buffer submission rejected or uncertain; reservation retained")
    state.update(state="queued", buffer_post_id=post["id"], due_at=post.get("dueAt"))
    original = ledger.api(rec)
    ledger.store(rec, state, "Confirm Buffer queue " + episode["id"],
                 old_sha=original["sha"])
    return {"queued": True, "episode": episode["id"], "buffer_post_id": post["id"],
            "due_at": post.get("dueAt")}


def main():
    p = argparse.ArgumentParser()
    for key in ("episode", "video", "metadata", "voice-qa", "mixed-qa"):
        p.add_argument("--" + key, required=True)
    args = p.parse_args()
    catalog = json.loads(Path(__file__).with_name("episodes.json").read_text("utf8"))
    episode = next((e for e in catalog["episodes"] if e["id"] == args.episode), None)
    if not episode:
        raise SystemExit("Episode not in catalog")
    voice = json.loads(Path(args.voice_qa).read_text("utf8"))
    mix = json.loads(Path(args.mixed_qa).read_text("utf8"))
    metadata = json.loads(Path(args.metadata).read_text("utf8"))
    print("BUFFER_AUTOPUBLISH", json.dumps(publish(
        episode, Path(args.video), metadata, voice, mix), ensure_ascii=False))


if __name__ == "__main__":
    main()
