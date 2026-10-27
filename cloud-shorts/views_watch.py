#!/usr/bin/env python3
"""Track real public YouTube view counts via the official Data API (no uploads).

Only public video metadata/statistics is requested. A restricted, free-quota
YouTube Data API key must be stored as a GitHub Actions secret; do not commit it.
Snapshots go to a separate GitHub branch so the channel's history is durable.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

VIDEO_ID = "26FQE80Io-Y"
EXPECTED_CHANNEL = "UCS0QCodPcFBTjMt4ioEWOUw"
LEDGER_BRANCH = "views-ledger"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
MAX_RESP = 256_000


def parse_video(body, expected_video=VIDEO_ID, expected_channel=EXPECTED_CHANNEL):
    """Verify exact video/channel before trusting counters."""
    if not isinstance(body, dict) or not isinstance(body.get("items"), list):
        raise ValueError("Invalid YouTube Data API response")
    items = [x for x in body["items"] if x.get("id") == expected_video]
    if len(items) != 1:
        raise ValueError("Target YouTube video absent or duplicated")
    item = items[0]
    snippet = item.get("snippet") or {}
    if snippet.get("channelId") != expected_channel:
        raise ValueError("Unexpected channel; do not record other people's videos")
    stats = item.get("statistics") or {}
    if not re.fullmatch(r"\d+", str(stats.get("viewCount", ""))):
        raise ValueError("Missing reliable public viewCount")
    data = {
        "video_id": expected_video,
        "channel_id": expected_channel,
        "title": str(snippet.get("title", ""))[:160],
        "views": int(stats["viewCount"]),
        "likes": int(stats["likeCount"]) if str(stats.get("likeCount", "")).isdigit() else None,
        "comments": int(stats["commentCount"]) if str(stats.get("commentCount", "")).isdigit() else None,
        "source": "official_youtube_data_api_v3",
    }
    return data


def diff_stats(current, previous):
    if not previous or previous.get("views") is None:
        return {"delta_views": None, "views_per_hour": None, "elapsed_hours": None}
    try:
        t1 = datetime.fromisoformat(current["observed_at"].replace("Z", "+00:00"))
        t0 = datetime.fromisoformat(previous["observed_at"].replace("Z", "+00:00"))
        elapsed = max(0.0, (t1 - t0).total_seconds() / 3600.0)
        delta = current["views"] - int(previous["views"])
    except (KeyError, TypeError, ValueError):
        return {"delta_views": None, "views_per_hour": None, "elapsed_hours": None}
    return {
        "delta_views": delta,
        "elapsed_hours": round(elapsed, 2),
        "views_per_hour": round(delta / elapsed, 1) if elapsed > 0.1 else None,
    }


def yt_public_stats(key, video=VIDEO_ID):
    if not VIDEO_ID_RE.fullmatch(video):
        raise ValueError("Invalid video ID")
    if not key:
        raise RuntimeError("YOUTUBE_DATA_API_KEY secret is missing")
    query = urllib.parse.urlencode({
        "key": key, "id": video, "part": "statistics,snippet",
        "fields": "items(id,snippet(channelId,title),statistics(viewCount,likeCount,commentCount))",
    })
    # URL contains API key. Never print its value or errors that include it.
    req = urllib.request.Request(
        "https://www.googleapis.com/youtube/v3/videos?" + query,
        headers={"User-Agent": "MotoShortsCloud-ViewsMonitor/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            payload = resp.read(MAX_RESP + 1)
            if len(payload) > MAX_RESP:
                raise ValueError("Unexpectedly large YouTube response")
    except urllib.error.HTTPError as err:
        raise RuntimeError("YouTube API request failed with HTTP " + str(err.code)) from None
    except urllib.error.URLError:
        raise RuntimeError("YouTube API network request failed") from None
    return parse_video(json.loads(payload), video)


def gh_base():
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise RuntimeError("GITHUB_REPOSITORY is not set")
    return "https://api.github.com/repos/" + repo + "/contents/"


def gh_headers():
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN missing")
    return {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "moto-shorts-cloud-views-watch",
    }


def gh_fetch(path):
    url = gh_base() + urllib.parse.quote(path, safe="/") + "?ref=" + LEDGER_BRANCH
    req = urllib.request.Request(url, headers=gh_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return None
        raise RuntimeError("GitHub ledger read HTTP " + str(err.code)) from None


def previous_snapshot(video=VIDEO_ID):
    records = gh_fetch("views/" + video)
    if not records:
        return None
    candidates = sorted(
        (x for x in records if x.get("type") == "file" and x.get("name", "").endswith(".json")),
        key=lambda x: x["name"], reverse=True
    )
    for item in candidates[:8]:
        entry = gh_fetch("views/" + video + "/" + item["name"])
        if entry and entry.get("content"):
            try:
                record = json.loads(base64.b64decode(entry["content"]))
                if record.get("video_id") == video and isinstance(record.get("views"), int):
                    return record
            except (ValueError, KeyError):
                continue
    return None


def save_snapshot(entry):
    stamp = datetime.fromisoformat(entry["observed_at"].replace("Z", "+00:00"))
    name = stamp.strftime("%Y-%m-%dT%H") + ".json"
    path = "views/" + VIDEO_ID + "/" + name
    old = gh_fetch(path)
    content = base64.b64encode(
        (json.dumps(entry, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf8")
    ).decode("ascii")
    payload = {
        "message": "Record YouTube Shorts public views " + stamp.strftime("%Y-%m-%d %H:%M UTC"),
        "branch": LEDGER_BRANCH,
        "content": content,
    }
    if old and old.get("sha"):
        payload["sha"] = old["sha"]
    request = urllib.request.Request(
        gh_base() + urllib.parse.quote(path, safe="/"), method="PUT",
        headers={**gh_headers(), "Content-Type": "application/json"},
        data=json.dumps(payload).encode("utf8"),
    )
    try:
        with urllib.request.urlopen(request, timeout=40) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as err:
        raise RuntimeError("GitHub ledger write HTTP " + str(err.code)) from None


def main():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    item = yt_public_stats(os.environ.get("YOUTUBE_DATA_API_KEY", "").strip())
    item["observed_at"] = now.isoformat().replace("+00:00", "Z")
    prev = previous_snapshot()
    if prev and prev.get("source") == "youtube_studio_baseline":
        # Studio baseline may use slightly different update timing; allow comparison,
        # but do not treat a temporary decrease as a sign of manipulation.
        item["baseline_source_note"] = "Prior Studio and API counts can refresh asynchronously"
    item.update(diff_stats(item, prev))
    save_snapshot(item)
    report = (
        f"Shorts [{VIDEO_ID}](https://www.youtube.com/shorts/{VIDEO_ID}): "
        f"**{item['views']} views**, {item['likes']} likes, "
        f"{item['comments']} comments; "
        f"change since previous snapshot: {item['delta_views']}, "
        f"views/hour: {item['views_per_hour']}."
    )
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf8") as output:
            output.write("### Public YouTube views check\n\n" + report + "\n\n")
    return item


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        # Exceptions are sanitized; never echo API key.
        print("VIEW_TRACKER_STOPPED", type(ex).__name__, str(ex), file=sys.stderr)
        raise SystemExit(1)
