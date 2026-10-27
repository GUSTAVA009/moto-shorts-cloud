#!/usr/bin/env python3
"""Automated cloud preview queue: each approved episode is rendered once.

This queue is NOT a YouTube publisher. It never auto-publishes or edits
any existing video; it only creates video drafts for owner review.
"""
from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BRANCH = "render-ledger"
EPISODES = Path(__file__).with_name("episodes.json")


def api(path, method="GET", data=None):
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise RuntimeError("Missing GitHub Actions authentication")
    url = "https://api.github.com/repos/" + repo + "/contents/" + urllib.parse.quote(path, safe="/")
    if method == "GET":
        url += "?ref=" + BRANCH
    headers = {
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "moto-shorts-cloud-queue",
    }
    request = urllib.request.Request(
        url, headers=headers, method=method,
        data=json.dumps(data).encode("utf8") if data else None,
    )
    try:
        with urllib.request.urlopen(request, timeout=28) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        if method == "GET" and err.code == 404:
            return None
        raise RuntimeError("GitHub queue operation failed HTTP " + str(err.code)) from None


def item_path(slug):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,46}", slug):
        raise ValueError("Invalid episode ID")
    return "render-receipts/" + slug + ".json"


def store(path, body, message, old_sha=None):
    payload = {
        "message": message, "branch": BRANCH,
        "content": base64.b64encode(
            (json.dumps(body, ensure_ascii=False, indent=2) + "\n").encode("utf8")
        ).decode("ascii"),
    }
    if old_sha:
        payload["sha"] = old_sha
    return api(path, "PUT", payload)


def pick(episodes, exists):
    """Pure helper: select first explicitly approved, never-reserved item."""
    for ep in episodes:
        if ep.get("auto_preview") is True and not exists(ep["id"]):
            return ep["id"]
    return None


def choose(catalog, output):
    data = json.loads(Path(catalog).read_text(encoding="utf8"))
    ep = pick(data["episodes"], lambda slug: api(item_path(slug)) is not None)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if ep is None:
        output.write_text("has_job=false\n", encoding="utf8")
        print("QUEUE_EMPTY; no duplicate Shorts will be rendered")
        return
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not run_id.isdigit():
        raise RuntimeError("Missing GitHub run identifier")
    record = {
        "id": ep, "state": "reserved", "run_id": run_id,
        "notes": "If render failed, inspect and reconcile before retry."
    }
    store(item_path(ep), record, "Reserve fresh Shorts preview " + ep)
    output.write_text("has_job=true\nepisode=" + ep + "\n", encoding="utf8")
    print("QUEUE_RESERVED", ep)


def finish(slug):
    path = item_path(slug)
    item = api(path)
    if item is None:
        raise RuntimeError("Render reservation missing")
    contents = json.loads(base64.b64decode(item["content"]))
    if contents.get("run_id") != os.environ.get("GITHUB_RUN_ID") or contents.get("state") != "reserved":
        raise RuntimeError("Render reservation changed; no auto-retry")
    contents["state"] = "preview_ready"
    store(path, contents, "Rendered unique Shorts preview " + slug, item["sha"])
    print("QUEUE_PREVIEW_READY", slug)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["choose", "finish"])
    p.add_argument("--catalog", type=Path, default=EPISODES)
    p.add_argument("--output", type=Path, default=Path("queue.properties"))
    p.add_argument("--episode", default="")
    args = p.parse_args()
    if args.action == "choose":
        choose(args.catalog, args.output)
    else:
        finish(args.episode)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("QUEUE_STOPPED", str(e), file=sys.stderr)
        raise SystemExit(1)
