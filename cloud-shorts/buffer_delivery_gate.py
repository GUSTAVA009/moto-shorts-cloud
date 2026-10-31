#!/usr/bin/env python3
"""Fail-closed proof of actual Buffer delivery before chaining next uploader.

One accepted, uniquely identified Buffer post may dispatch one next workflow.
An absent, skipped, failed, or ambiguous response must never cause a loop.
"""
import argparse
import json
import os
from pathlib import Path
import urllib.request

REPOSITORY = "GUSTAVA009/moto-shorts-cloud"
WORKFLOW = "buffer-backlog.yml"


def parse_confirmed(log):
    lines = [line.strip() for line in str(log).splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("BUFFER_DELIVERY_UNCONFIRMED: empty response")
    try:
        final = lines[-1]
        if final.startswith("BUFFER_AUTOPUBLISH "):
            final = final.split(" ", 1)[1]
        response = json.loads(final)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("BUFFER_DELIVERY_UNCONFIRMED: missing final JSON") from exc
    if (not isinstance(response, dict)
            or response.get("queued") is not True
            or not isinstance(response.get("episode"), str)
            or not response["episode"].strip()
            or not isinstance(response.get("buffer_post_id"), str)
            or not response["buffer_post_id"].strip()
            or not isinstance(response.get("due_at"), str)
            or "T" not in response["due_at"]):
        raise RuntimeError("BUFFER_DELIVERY_UNCONFIRMED: no scheduled Buffer post ID")
    return response


def confirm(log_path, output_path):
    obj = parse_confirmed(Path(log_path).read_text(encoding="utf8"))
    with Path(output_path).open("a", encoding="utf8") as out:
        out.write("queued=true\n")
    print("BUFFER_ID_AND_SCHEDULE_CONFIRMED",
          obj["episode"], obj["buffer_post_id"], obj["due_at"], flush=True)
    return obj


def dispatch_next(token, repo, urlopen=urllib.request.urlopen):
    if repo != REPOSITORY or not token:
        raise RuntimeError("UNAUTHORIZED_BUFFER_QUEUE_REFILL")
    url = "https://api.github.com/repos/" + REPOSITORY + (
        "/actions/workflows/" + WORKFLOW + "/dispatches")
    req = urllib.request.Request(
        url, data=json.dumps({"ref": "main"}).encode("utf8"), method="POST",
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "gustava-buffer-confirmed-chain"})
    with urlopen(req, timeout=30) as response:
        if response.status != 204:
            raise RuntimeError("BUFFER_QUEUE_REFILL_DISPATCH_REJECTED")
    print("BUFFER_CONFIRMED_NEXT_UNIQUE_SEND_DISPATCHED", flush=True)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="action", required=True)
    c = sub.add_parser("confirm")
    c.add_argument("--log", type=Path, required=True)
    c.add_argument("--output", type=Path, required=True)
    sub.add_parser("dispatch")
    a = p.parse_args()
    if a.action == "confirm":
        confirm(a.log, a.output)
    else:
        dispatch_next(os.getenv("GITHUB_TOKEN", ""),
                      os.getenv("GITHUB_REPOSITORY", ""))


if __name__ == "__main__":
    main()
