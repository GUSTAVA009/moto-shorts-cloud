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
from editorial_novelty import is_repeated_visual_formula
from visual_director import verify_story_subject
from deep_voice import (PROFILE_ID as REQUIRED_MALE_PROFILE,
                        VOICE_ENGINE as REQUIRED_MALE_ENGINE,
                        ready as deep_audio_ready)


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
    "render_episode.py", "caption_layout.py", "tts_voice.py", "silero_voice.py",
    "soundtrack.py", "kokoro_voice.py", "voice_qa.py", "mixed_audio_qa.py",
    "asr_fallback.py", "qa_autorepair.py", "moto_assets.py", "voice_style.py", "native_bass_voice.py", "silero_voice.py", "deep_voice.py",
)
MAX_ATTEMPTS = 3
MAX_VISUAL_REPAIR_ATTEMPTS = 4  # one confirmed frozen-footage correction before any upload
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
    visual_repair = (episode.get("visual_revision_requested") is True
                     and episode.get("visual_revision_reason") in (
                         "source_freeze_confirmed",
                         "owner_rejected_static_helmet_coverage",
                         "owner_rejected_end_clip_no_helmet_removal",
                         "caption_clipped_confirmed"))
    male_voice_repair = (
        episode.get("voice_engine") == REQUIRED_MALE_ENGINE
        and episode.get("voice_revision_requested") is True
        and episode.get("voice_profile") == REQUIRED_MALE_PROFILE
        and receipt.get("voice_profile") != REQUIRED_MALE_PROFILE
    )
    limit = (MAX_DOCUMENTARY_ATTEMPTS if
             episode.get("episode_series", {}).get("historical_reconstruction")
             else MAX_VISUAL_REPAIR_ATTEMPTS
             if visual_repair or male_voice_repair else MAX_ATTEMPTS)
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
        # An unrelated code change (mastering, metadata, dependencies) is
        # NOT permission to remake an already passing Deep video. A completed
        # DEEP preview can be re-recorded only with a *different, audited*
        # provider MP3 hash pinned to the same episode, or when correcting
        # explicitly documented visual failures. Receipts predating the proof
        # field fail closed rather than guessing.
        source = (episode.get("deep_audio") or {}).get("source_audio_sha256")
        previous_source = receipt.get("deep_source_sha256")
        genuine_new_deep = (
            episode.get("voice_revision_requested") is True
            and episode.get("auto_publish") is not True
            and episode.get("voice_engine") == REQUIRED_MALE_ENGINE
            and isinstance(source, str) and bool(re.fullmatch(r"[0-9a-f]{64}", source))
            and isinstance(previous_source, str)
            and bool(re.fullmatch(r"[0-9a-f]{64}", previous_source))
            and source != previous_source
        )
        return bool(
            episode.get("episode_series", {}).get("historical_reconstruction")
            or visual_repair
            or male_voice_repair
            or genuine_new_deep
        )
    return True


def eligible_abandoned_source_retry(episode, receipt, new_fingerprint, old_conclusion):
    """Recover only an explicitly revised source from a completed failed Actions run."""
    if not isinstance(receipt, dict) or receipt.get("id") != episode.get("id"):
        return False
    if receipt.get("state") != "reserved":
        return False
    if episode.get("source_revision_requested") is not True:
        return False
    if episode.get("source_revision_reason") not in (
            "oversized_source_replaced", "unavailable_source_replaced",
            "frozen_source_replaced", "oversized_source_bounded_stream",
            "short_helmet_adjustment_rebalanced",
            "undersized_source_motion_verified"):
        return False
    attempt = receipt.get("attempt_count", 1)
    if type(attempt) is not int or attempt < 1:
        return False
    if receipt.get("preview_fingerprint") == new_fingerprint:
        return False
    # A verified frozen licensed source, NOT a failed voice or already
    # rendered/published MP4, may receive one extra private source repair
    # after the third unsuccessful render. Confirm both media identity
    # change and exact prior failed run; selector checks GitHub conclusion
    # and permanent publication receipts separately.
    if attempt >= MAX_ATTEMPTS:
        proof = episode.get("source_replacement_proof")
        if not (attempt == MAX_ATTEMPTS
                and episode.get("auto_preview") is True
                and episode.get("auto_publish") is False
                and episode.get("voice_engine") == REQUIRED_MALE_ENGINE
                and episode.get("source_revision_reason") == "frozen_source_replaced"
                and isinstance(proof, dict)
                and proof.get("old_failure") == "VISUAL_FROZEN_SEGMENT"
                and proof.get("failed_run_id") == str(receipt.get("run_id"))
                and old_conclusion == "failure"):
            return False
        old_media = proof.get("old_source_id", "")
        new_media = proof.get("new_source_id", "")
        if (not isinstance(old_media, str) or not old_media.isdigit()
                or not isinstance(new_media, str) or not new_media.isdigit()
                or old_media == new_media):
            return False
        sources = {str(m.get("source_page") or "").rstrip("/")
                   for m in episode.get("footage") or []}
        if (not any(u.endswith("/" + new_media) for u in sources)
                or any(u.endswith("/" + old_media) for u in sources)):
            return False
        return True
    return old_conclusion in ("failure", "cancelled", "timed_out")


def eligible_abandoned_audio_config_retry(episode, receipt, new_fingerprint, old_conclusion):
    """Recover one exact unpublished failed job after a genuine DSP config fix.

    This cannot grant a second YouTube upload and only accepts an explicitly
    named audio-repair reason. The previous GitHub run must be verified closed.
    """
    if not isinstance(receipt, dict) or receipt.get("id") != episode.get("id"):
        return False
    if receipt.get("state") != "reserved":
        return False
    if episode.get("technical_revision_requested") is not True:
        return False
    if episode.get("technical_revision_reason") != "safe_music_gain_range_fixed":
        return False
    if not (episode.get("auto_preview") is True and episode.get("auto_publish") is True):
        return False
    attempts = receipt.get("attempt_count", 1)
    if type(attempts) is not int or not 1 <= attempts < MAX_ATTEMPTS:
        return False
    if receipt.get("preview_fingerprint") == new_fingerprint:
        return False
    return old_conclusion in ("failure", "cancelled", "timed_out")


def eligible_abandoned_visual_duration_retry(episode, receipt, new_fingerprint, old_conclusion):
    """One bounded retry for confirmed visual-duration failure on original Deep.

    Never relax ASR, repeat footage, or authorize public release as a side effect.
    """
    if not isinstance(receipt, dict) or receipt.get("id") != episode.get("id"):
        return False
    if receipt.get("state") != "reserved" or old_conclusion not in (
            "failure", "cancelled", "timed_out"):
        return False
    if (episode.get("visual_duration_revision_requested") is not True
            or episode.get("visual_duration_revision_reason") !=
                "two_active_moving_scenes_not_long_enough"):
        return False
    if (episode.get("auto_preview") is not True
            or episode.get("auto_publish") is not False
            or episode.get("voice_engine") != REQUIRED_MALE_ENGINE
            or int(episode.get("visual_director_version") or 0) != 3):
        return False
    source_keys = {x.get("key") for x in episode.get("footage") or []}
    shots = episode.get("shots") or []
    if (len(source_keys) != 2 or len(shots) != 2
            or {x.get("source") for x in shots} != source_keys):
        return False
    try:
        cap = float(episode.get("active_ride_scene_seconds"))
    except (TypeError, ValueError):
        return False
    if not 9.0 <= cap <= 10.0:
        return False
    attempts = receipt.get("attempt_count", 1)
    return (type(attempts) is int and 1 <= attempts < MAX_ATTEMPTS
            and receipt.get("preview_fingerprint") != new_fingerprint)


def failed_action_conclusion(run_id):
    """Fail closed unless GitHub confirms the prior render job terminated."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not str(run_id).isdigit() or not token or repo != "GUSTAVA009/moto-shorts-cloud":
        raise RuntimeError("Unverifiable reserved render; never start parallel retry")
    url = "https://api.github.com/repos/" + repo + "/actions/runs/" + str(run_id)
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "gustava-verified-reservation-recovery",
    })
    with urllib.request.urlopen(req, timeout=25) as response:
        data = json.load(response)
    if data.get("id") != int(run_id) or data.get("status") != "completed":
        raise RuntimeError("Prior render still running or missing; no recovery permitted")
    return data.get("conclusion")


def verified_failed_preflight(run_id):
    """A retry is allowed only if GitHub proves the runner failed *before render*."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if (not str(run_id).isdigit() or not token
            or repo != "GUSTAVA009/moto-shorts-cloud"):
        raise RuntimeError("Cannot prove failed DEEP bootstrap")
    root = "https://api.github.com/repos/" + repo + "/actions/"
    headers = {"Authorization": "Bearer " + token,
               "Accept": "application/vnd.github+json",
               "User-Agent": "gustava-strict-bootstrap-recovery"}
    def read(suffix):
        req = urllib.request.Request(root + suffix, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)
    run = read("runs/" + str(run_id))
    if (run.get("id") != int(run_id) or run.get("status") != "completed"
            or run.get("conclusion") != "failure"):
        return False
    jobs = read("runs/" + str(run_id) + "/jobs?per_page=100")
    if jobs.get("total_count", 0) > 100:
        raise RuntimeError("Incomplete bootstrap job evidence")
    for job in jobs.get("jobs", []):
        if (job.get("name") != "daily-draft"
                or job.get("status") != "completed"
                or job.get("conclusion") != "failure"):
            continue
        steps = {step.get("name"): step.get("conclusion")
                 for step in job.get("steps", [])}
        if (steps.get("Install free audio/video engines") == "failure"
                and steps.get("Render and automatically repair bad narration or voice masking (maximum three QA attempts)")
                    in ("skipped", None)
                and steps.get("Mark one-off preview as completed") != "success"):
            return True
    return False


def eligible_abandoned_bootstrap_retry(episode, receipt, new_fingerprint, bootstrap_proved):
    """Recover a *private* MP4 attempt that died installing retired TTS packages.

    Never retries unchanged code, a published/approved release, an in-flight job,
    or one whose runner actually started rendering video. The separate selector
    also checks permanent YouTube/Buffer receipts before any write.
    """
    return bool(
        bootstrap_proved is True
        and episode.get("auto_preview") is True
        and episode.get("auto_publish") is False
        and episode.get("voice_engine") == REQUIRED_MALE_ENGINE
        and isinstance(receipt, dict)
        and receipt.get("id") == episode.get("id")
        and receipt.get("state") == "reserved"
        and type(receipt.get("attempt_count")) is int
        and 1 <= receipt["attempt_count"] < MAX_ATTEMPTS
        and receipt.get("preview_fingerprint") != new_fingerprint
    )


def choose(catalog, output):
    data = json.loads(Path(catalog).read_text(encoding="utf8"))
    validate_catalog(data)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    listed = []
    for ep in data["episodes"]:
        if ep.get("auto_preview") is not True or not deep_audio_ready(ep):
            continue
        if (ep.get("editorial_rejected") is True
                or is_repeated_visual_formula(ep, data["episodes"])):
            print("REPETITIVE_VIDEO_BLOCKED", ep["id"], flush=True)
            continue
        try:
            verify_story_subject(ep)
        except ValueError as exc:
            print("VISUAL_STORY_REJECTED_BEFORE_RESERVATION",ep["id"],str(exc)[:300],flush=True)
            continue
        listed.append(ep)
    print("GUSTAVA_DEEP_AND_VISUAL_READY_EPISODES",len(listed),flush=True)
    def unpublished(slug):
        # Legacy uploads and Buffer reservations both block rerenders.
        return (api("publication-receipts/" + slug + ".json") is None
                and api("buffer-publication-receipts/" + slug + ".json") is None)
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
    # Genuine NEW originals have priority over recycling older private
    # revisions. A newly sourced story with hash-pinned DEEP must not wait
    # behind old clips repeatedly submitted for visual fixes.
    if selected is None:
        selected = next((ep for ep in listed
                         if records[ep["id"]][0] is None
                         and unpublished(ep["id"])), None)
    # An explicit, unpublished narration repair has priority over historical
    # retries. It cannot target a published video, only a revised preview.
    if selected is None:
        for item in sorted(listed, key=lambda ep: (0 if (ep.get("caption_repair_priority") is True and ep.get("caption_fit_required") is True and ep.get("auto_publish") is False) else 1, 0 if ep.get("voice_revision_priority") is True else 1)):
            if not (item.get("voice_revision_requested") is True
                    or item.get("visual_revision_requested") is True):
                continue
            _, receipt = records[item["id"]]
            if eligible_retry(item, receipt, preview_fingerprint(item)):
                if unpublished(item["id"]):
                    selected = item
                    break
    # Recover a failed, unpublished source download OR a tightly audited
    # safe audio-configuration repair. Never allow public/parallel retries.
    if selected is None:
        for item in listed:
            if not (item.get("source_revision_requested") is True
                    or item.get("technical_revision_requested") is True
                    or item.get("visual_duration_revision_requested") is True):
                continue
            _, receipt = records[item["id"]]
            if not receipt or receipt.get("state") != "reserved":
                continue
            if not unpublished(item["id"]):
                continue
            new_fp = preview_fingerprint(item)
            if receipt.get("preview_fingerprint") == new_fp:
                continue
            outcome = failed_action_conclusion(receipt.get("run_id"))
            if (eligible_abandoned_source_retry(item, receipt, new_fp, outcome)
                    or eligible_abandoned_audio_config_retry(item, receipt, new_fp, outcome)
                    or eligible_abandoned_visual_duration_retry(
                        item, receipt, new_fp, outcome)):
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
                if unpublished(item["id"]):
                    selected = item
                    break
    # An install-only technical failure must not permanently consume an
    # unpublished original DEEP recording. Confirm exact failed GitHub job
    # and a changed render/ASR fingerprint before a bounded recovery.
    if selected is None:
        for item in listed:
            if item.get("auto_publish") is not False:
                continue
            _, receipt = records[item["id"]]
            if (not receipt or receipt.get("state") != "reserved"
                    or receipt.get("attempt_count", MAX_ATTEMPTS) >= MAX_ATTEMPTS
                    or not unpublished(item["id"])):
                continue
            new_fp = preview_fingerprint(item)
            if receipt.get("preview_fingerprint") == new_fp:
                continue
            proof = verified_failed_preflight(receipt.get("run_id"))
            if eligible_abandoned_bootstrap_retry(item, receipt, new_fp, proof):
                selected = item
                print("VERIFIED_INSTALL_FAILED_DEEP_RETRY", item["id"],
                      "previous", receipt.get("run_id"), flush=True)
                break
    # Published/cleared originals are not retried. Failed unreleased, approved
    # Shorts can be improved only when the text or sound engine was revised.
    if selected is None:
        for item in listed:
            if item.get("auto_publish") is not True:
                continue
            _, receipt = records[item["id"]]
            if eligible_retry(item, receipt, preview_fingerprint(item)):
                if unpublished(item["id"]):
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
        "deep_source_sha256": (item.get("deep_audio") or {}).get("source_audio_sha256"),
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
    contents["voice_profile"] = report.get("voice_profile")
    contents["male_voice_verified"] = report.get("male_voice_verified") is True
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
