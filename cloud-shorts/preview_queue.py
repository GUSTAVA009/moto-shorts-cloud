#!/usr/bin/env python3
"""Automated cloud preview queue: each approved episode is rendered once.

This queue is NOT a YouTube publisher. It never auto-publishes or edits
any existing video; it only creates video drafts for owner review.
"""
from __future__ import annotations
import argparse
import base64
import binascii
import json
import hashlib
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BRANCH = "render-ledger"
EPISODES = Path(__file__).with_name("episodes.json")
HISTORY_PATH = "history/used_footage.json"

from editorial_guard import source_id, validate_catalog


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


def decode_history(entry):
    """Refuse any clip if the persistent footage ledger is unavailable."""
    if not entry or not isinstance(entry.get("content"), str) or not entry["content"].strip() or not entry.get("sha"):
        raise RuntimeError("Persistent used-footage ledger missing: refuse to render")
    try:
        history = json.loads(base64.b64decode("".join(entry["content"].split()), validate=True))
    except (ValueError, TypeError, UnicodeDecodeError, binascii.Error):
        raise RuntimeError("Corrupt permanent footage registry") from None
    if history.get("version") != 1 or not isinstance(history.get("used"), dict):
        raise RuntimeError("Invalid permanent footage registry")
    return history


def assert_new_sources(episode, history):
    for source in episode["footage"]:
        sid = source_id(source)
        prev = history["used"].get(sid)
        if prev is not None and prev.get("episode") != episode["id"]:
            raise RuntimeError(
                "PERMANENT_SOURCE_REUSE_BLOCKED: " + sid + " already in "
                + str(prev.get("episode"))
            )


RENDER_DEPENDENCIES = (
    "render_episode.py", "tts_voice.py", "silero_voice.py",
    "soundtrack.py", "kokoro_voice.py", "voice_qa.py", "mixed_audio_qa.py",
    "asr_fallback.py",
)
MAX_ATTEMPTS = 3
MAX_DOCUMENTARY_ATTEMPTS = 5  # extra licensed visual corrections, unpublished only


def preview_fingerprint(episode):
    """Change only when actual narration, visuals or render/QA implementation changes."""
    spec = {k: v for k, v in episode.items()
            if k not in ("auto_preview", "auto_publish")}
    h = hashlib.sha256(json.dumps(
        spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf8"))
    for filename in RENDER_DEPENDENCIES:
        path = Path(__file__).with_name(filename)
        if not path.is_file():
            raise RuntimeError("Missing core render dependency: " + filename)
        h.update(filename.encode("ascii"))
        h.update(path.read_bytes())
    return h.hexdigest()


def decode_receipt(entry):
    """Do not accept a broken ledger entry as permission to republish."""
    if entry is None:
        return None
    if not isinstance(entry.get("content"), str) or not entry.get("sha"):
        raise RuntimeError("Corrupt render receipt")
    try:
        record = json.loads(base64.b64decode(entry["content"], validate=False))
    except (ValueError, TypeError, binascii.Error) as exc:
        raise RuntimeError("Invalid render receipt: no blind retry") from exc
    if not isinstance(record, dict) or not record.get("id"):
        raise RuntimeError("Invalid render receipt shape")
    return record


def eligible_retry(episode, receipt, new_fingerprint):
    """Rerender only a genuinely revised, never-published failed preview."""
    if receipt is None or receipt.get("id") != episode["id"]:
        return False
    if receipt.get("state") != "preview_ready":
        return False
    attempts = int(receipt.get("attempt_count", 1))
    limit = (MAX_DOCUMENTARY_ATTEMPTS if
             episode.get("episode_series", {}).get("historical_reconstruction") else MAX_ATTEMPTS)
    if not 1 <= attempts < limit:
        return False
    # Real-event documentaries may pass language QA but still have factually
    # misleading illustrations. A verified editorial/media revision is worth
    # one bounded unpublished replacement preview (not a YouTube re-upload).
    changed = receipt.get("preview_fingerprint") != new_fingerprint
    if not changed:
        return False
    if (receipt.get("voice_qa_passed") is True
            and receipt.get("mixed_audio_qa_passed") is True):
        # Allow one bounded correction of a truly revised, NEVER-PUBLISHED
        # non-serial preview if an explicit, named voice revision was requested.
        # The fingerprint must change and the logical episode cannot already
        # be permitted for public auto-release.
        return bool(
            episode.get("episode_series", {}).get("historical_reconstruction")
            or (episode.get("voice_revision_requested") is True
                and episode.get("auto_publish") is not True)
        )
    return True


def choose(catalog, output):
    data = json.loads(Path(catalog).read_text(encoding="utf8"))
    validate_catalog(data)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    listed = [ep for ep in data["episodes"] if ep.get("auto_preview") is True]
    records = {}
    for item in listed:
        entry = api(item_path(item["id"]))
        records[item["id"]] = (entry, decode_receipt(entry))
    # New, independently verified cross-niche pilots have priority for the
    # limited 14-day test. Never force a completed or reserved video to rerender.
    selected = next((ep for ep in listed
                     if ep.get("research_pillar") in ("engineering", "nature", "science",
                                                      "history", "space", "surprising_facts")
                     and records[ep["id"]][0] is None), None)
    # An explicit, unpublished narration repair has priority over historical
    # retries. It cannot target a published video, only a revised preview.
    if selected is None:
        for item in listed:
            if item.get("voice_revision_requested") is not True:
                continue
            _, receipt = records[item["id"]]
            if eligible_retry(item, receipt, preview_fingerprint(item)):
                if api("publication-receipts/" + item["id"] + ".json") is None:
                    selected = item
                    break
    # Historical serial continuity: repair part one before beginning part two,
    # but do not let repeated serial retries indefinitely block topic experiments.
    if selected is None:
        for item in listed:
            old_entry, receipt = records[item["id"]]
            if not item.get("episode_series"):
                continue
            if eligible_retry(item, receipt, preview_fingerprint(item)):
                if api("publication-receipts/" + item["id"] + ".json") is None:
                    selected = item
                    break
    # Then try any new licensed episode before retrying an old non-series clip.
    if selected is None:
        selected = next((ep for ep in listed if records[ep["id"]][0] is None), None)
    # Published/cleared originals are not retried. Failed unreleased, approved
    # Shorts can be improved only when the text or sound engine was revised.
    if selected is None:
        for item in listed:
            if item.get("auto_publish") is not True:
                continue
            _, receipt = records[item["id"]]
            if eligible_retry(item, receipt, preview_fingerprint(item)):
                if api("publication-receipts/" + item["id"] + ".json") is None:
                    selected = item
                    break
    if selected is None:
        output.write_text("has_job=false\n", encoding="utf8")
        print("QUEUE_EMPTY: no new or revised legally cleared video to render")
        return
    item = selected
    slug = item["id"]
    existing, old_receipt = records[slug]
    entry = api(HISTORY_PATH)
    history = decode_history(entry)
    assert_new_sources(item, history)
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not run_id.isdigit():
        raise RuntimeError("Missing GitHub run identifier")
    attempt = int(old_receipt.get("attempt_count", 1)) + 1 if old_receipt else 1
    record = {
        "id": slug, "state": "reserved", "run_id": run_id,
        "attempt_count": attempt,
        "preview_fingerprint": preview_fingerprint(item),
        "previous_run_id": old_receipt.get("run_id") if old_receipt else None,
        "notes": "Revised preview only; never retry a public or uncertain upload."
    }
    store(item_path(slug), record, "Reserve unique or revised Shorts preview " + slug,
          old_sha=existing["sha"] if existing else None)
    for source in item["footage"]:
        sid = source_id(source)
        history["used"][sid] = {
            "episode": slug, "source": source["source_page"],
            "status": "reserved-or-rendered",
        }
    history.setdefault("scene_profiles", {})[slug] = item["editorial"]
    store(HISTORY_PATH, history, "Record licensed sources for " + slug, entry["sha"])
    output.write_text("has_job=true\nepisode=" + slug + "\n", encoding="utf8")
    print("QUEUE_RESERVED", slug, "attempt", attempt)


def finish(slug, qa_report=None, mixed_report=None):
    path = item_path(slug)
    item = api(path)
    if item is None:
        raise RuntimeError("Render reservation missing")
    contents = json.loads(base64.b64decode(item["content"]))
    if contents.get("run_id") != os.environ.get("GITHUB_RUN_ID") or contents.get("state") != "reserved":
        raise RuntimeError("Render reservation changed; no auto-retry")
    contents["state"] = "preview_ready"
    # The independent ASR result is bound to the render receipt. Backlog
    # publishing may only select files with an explicit passing report.
    report = {}
    if qa_report and Path(qa_report).is_file():
        try:
            report = json.loads(Path(qa_report).read_text(encoding="utf8"))
        except (ValueError, OSError):
            report = {}
    contents["voice_qa_passed"] = (
        report.get("episode_id") == slug
        and report.get("passed") is True
        and report.get("status") == "passed"
        and report.get("final_word_present") is True
    )
    contents["voice_qa_coverage"] = report.get("lexical_coverage")
    mix = {}
    if mixed_report and Path(mixed_report).is_file():
        try:
            mix = json.loads(Path(mixed_report).read_text(encoding="utf8"))
        except (ValueError, OSError):
            mix = {}
    contents["mixed_audio_qa_passed"] = (
        mix.get("episode_id") == slug
        and mix.get("source") == "FINAL_MIXED_MP4"
        and mix.get("status") == "passed"
        and mix.get("passed") is True
        and mix.get("final_word_present") is True
        and mix.get("numerics_match") is True
        and mix.get("lexical_coverage", 0) >= .79
    )
    contents["mixed_audio_qa_coverage"] = mix.get("lexical_coverage")
    store(path, contents, "Rendered unique Shorts preview " + slug, item["sha"])
    print("QUEUE_PREVIEW_READY", slug)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["choose", "finish"])
    p.add_argument("--catalog", type=Path, default=EPISODES)
    p.add_argument("--output", type=Path, default=Path("queue.properties"))
    p.add_argument("--episode", default="")
    p.add_argument("--qa-report", type=Path, default=None)
    p.add_argument("--mixed-qa-report", type=Path, default=None)
    args = p.parse_args()
    if args.action == "choose":
        choose(args.catalog, args.output)
    else:
        finish(args.episode, args.qa_report, args.mixed_qa_report)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("QUEUE_STOPPED", str(e), file=sys.stderr)
        raise SystemExit(1)
