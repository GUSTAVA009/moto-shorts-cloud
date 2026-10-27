#!/usr/bin/env python3
"""Durable, fail-closed duplicate-upload protection using a separate GitHub branch.

Every video SHA256 + channel gets a reservation BEFORE YouTube upload. If the
upload or acknowledgement becomes uncertain, retries are blocked until a human
reconciles the reservation. Uses GITHUB_TOKEN from Actions, never a user PAT.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

LEDGER_BRANCH = "upload-ledger"
API_BASE = "https://api.github.com"
CHANNEL_RE = re.compile(r"^UC[-_A-Za-z0-9]{22}$")


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(2 ** 20), b""):
            h.update(block)
    return h.hexdigest()


def ledger_path(channel_id, video_sha):
    if not CHANNEL_RE.fullmatch(channel_id):
        raise ValueError("Invalid YouTube channel ID")
    if not re.fullmatch(r"[a-f0-9]{64}", video_sha):
        raise ValueError("Invalid video fingerprint")
    return f"upload-receipts/{channel_id}/{video_sha}.json"


def make_reservation(channel_id, video_sha, run_id):
    if not str(run_id).isdigit():
        raise ValueError("Missing/invalid GitHub run id")
    return {
        "status": "reserved", "channel_id": channel_id,
        "sha256": video_sha, "run_id": str(run_id),
        "warning": "Do not retry if upload outcome is uncertain; reconcile with YouTube Studio."
    }


def validate_receipt(reservation, receipt):
    for key in ("sha256", "channel_id"):
        if receipt.get(key) != reservation.get(key):
            raise ValueError("Upload receipt does not match reserved video/channel")
    video_id = receipt.get("video_id")
    if not isinstance(video_id, str) or not re.fullmatch(r"[-_A-Za-z0-9]{11}", video_id):
        raise ValueError("Invalid YouTube video id in receipt")
    return video_id


def headers():
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GITHUB_TOKEN missing; refuse any upload")
    return {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "moto-shorts-cloud-upload-guard",
        "Content-Type": "application/json",
    }


def repo_path(path):
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise RuntimeError("Missing GITHUB_REPOSITORY")
    encoded = urllib.parse.quote(path, safe="/")
    return API_BASE + "/repos/" + repo + "/contents/" + encoded


def get_entry(path):
    url = repo_path(path) + "?ref=" + LEDGER_BRANCH
    req = urllib.request.Request(url, headers=headers())
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            return json.load(res)
    except urllib.error.HTTPError as ex:
        if ex.code == 404:
            return None
        raise RuntimeError(f"Ledger read failed (HTTP {ex.code})") from None


def put_entry(path, obj, message, previous_sha=None):
    body = {
        "message": message,
        "branch": LEDGER_BRANCH,
        "content": base64.b64encode(
            (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf8")
        ).decode("ascii"),
    }
    if previous_sha:
        body["sha"] = previous_sha
    req = urllib.request.Request(repo_path(path),
        headers=headers(),
        method="PUT", data=json.dumps(body).encode("utf8"))
    try:
        with urllib.request.urlopen(req, timeout=35) as res:
            return json.load(res)
    except urllib.error.HTTPError as ex:
        raise RuntimeError(
            f"Ledger reservation/update refused (HTTP {ex.code}). "
            "No automatic retry; check existing reservation."
        ) from None


def reserve(video, channel, result_path):
    sha = file_hash(video)
    path = ledger_path(channel, sha)
    existing = get_entry(path)
    if existing:
        raise RuntimeError(
            "ALREADY_RESERVED: This video/channel is already registered. "
            "Check upload-ledger branch before retrying."
        )
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    obj = make_reservation(channel, sha, run_id)
    put_entry(path, obj, "Reserve YouTube upload " + sha[:14])
    result = {"path": path, **obj}
    Path(result_path).write_text(json.dumps(result, indent=2), encoding="utf8")
    print("UPLOAD_RESERVED", sha[:14], channel, "run", run_id)


def finish(reservation_path, receipt_path):
    reservation = json.loads(Path(reservation_path).read_text(encoding="utf8"))
    receipt = json.loads(Path(receipt_path).read_text(encoding="utf8"))
    video_id = validate_receipt(reservation, receipt)
    current = get_entry(reservation["path"])
    if not current:
        raise RuntimeError("Reservation disappeared; do not retry YouTube upload.")
    file_bytes = base64.b64decode(current["content"])
    stored = json.loads(file_bytes)
    if stored.get("run_id") != reservation.get("run_id") or stored.get("status") != "reserved":
        raise RuntimeError("Reservation state changed; manual review required")
    stored.update({
        "status": "uploaded", "video_id": video_id,
        "youtube_url": "https://www.youtube.com/watch?v=" + video_id,
        "privacy_requested": receipt.get("privacy_requested", "private"),
    })
    put_entry(reservation["path"], stored,
              "Confirm YouTube upload " + video_id,
              previous_sha=current["sha"])
    print("UPLOAD_CONFIRMED", stored["youtube_url"])


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="mode", required=True)
    a = sub.add_parser("reserve")
    a.add_argument("--video", required=True, type=Path)
    a.add_argument("--channel", required=True)
    a.add_argument("--output", required=True, type=Path)
    b = sub.add_parser("finish")
    b.add_argument("--reservation", required=True, type=Path)
    b.add_argument("--receipt", required=True, type=Path)
    args = p.parse_args()
    try:
        if args.mode == "reserve":
            reserve(args.video, args.channel, args.output)
        else:
            finish(args.reservation, args.receipt)
    except Exception as exc:
        print("UPLOAD_GUARD_STOPPED:", str(exc), file=sys.stderr)
        sys.exit(1)
