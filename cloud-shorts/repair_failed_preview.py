#!/usr/bin/env python3
"""One bounded autonomous Russian script repair for a FAILED, UNPUBLISHED Short.

Runs only after a completed failed preview with an attached independent ASR QA
report. It never changes a public upload, never lowers QA thresholds, never
copies ASR mistakes into narration and never retries a reserved/unknown post.
"""
from __future__ import annotations

import base64
import copy
import json
import os
from pathlib import Path
import re
import sys

import preview_queue as ledger
from editorial_guard import validate_catalog
from render_episode import validate_episode
from voice_qa import tokens
from autofill_catalog import github

CATALOG = "cloud-shorts/episodes.json"
MAX_REVISION_ATTEMPTS = 3
SAFE_REWRITES = (
    ("с осмотра", "с простой проверки"),
    ("на мотоцикле", "на своём байке"),
    ("выбирай темп", "подбирай скорость"),
    ("выбери темп", "подбери скорость"),
    ("дождевой дороге", "мокрой дороге"),
    ("дороги", "трассы"),
    ("на ладонях", "в руках"),
    ("предупредить", "сказать заранее"),
    ("не торопись", "не спеши"),
)
MAX_LEN = 350


def simple_rewrite(expected, heard):
    """Change only a bounded, acoustically ambiguous turn of phrase.

    A recognized wrong word is NEVER treated as the ground truth. We change a
    phrase only if at least one expected token is absent from the old ASR.
    """
    heard_set = set(tokens(heard))
    for old, new in SAFE_REWRITES:
        if old in expected.casefold() and not set(tokens(old)).issubset(heard_set):
            updated = re.sub(re.escape(old), new, expected, count=1, flags=re.I)
            if updated != expected and 55 <= len(updated) <= MAX_LEN:
                return updated
    return None


def repair_episode(catalog, ep_id, voice_qa, mixed_qa, receipt):
    if not isinstance(receipt, dict) or receipt.get("id") != ep_id:
        return None
    if receipt.get("state") != "preview_ready":
        return None
    if receipt.get("voice_qa_passed") is True and receipt.get("mixed_audio_qa_passed") is True:
        return None
    count = int(receipt.get("attempt_count") or 0)
    if not 1 <= count < MAX_REVISION_ATTEMPTS:
        return None
    if voice_qa.get("episode_id") != ep_id or mixed_qa.get("episode_id") != ep_id:
        return None
    if voice_qa.get("passed") is True and mixed_qa.get("passed") is True:
        return None
    episodes = catalog.get("episodes", [])
    old = next((x for x in episodes if x["id"] == ep_id), None)
    if not old or old.get("auto_publish") is not True or old.get("voice_engine") != "kokoro_ru_dima":
        return None
    # Raw narration first; if it was fine, keep exact script and let an audio
    # specialist review a remaining mix defect rather than mis-editing words.
    if voice_qa.get("passed") is True:
        return None
    recognized = str(voice_qa.get("recognized_text") or "")
    new_text = simple_rewrite(old["narration"], recognized)
    if not new_text:
        return None
    candidate = copy.deepcopy(catalog)
    ep = next(x for x in candidate["episodes"] if x["id"] == ep_id)
    ep["narration"] = new_text
    ep["voice_revision_requested"] = True
    ep["voice_revision_note"] = (
        "Automatic bounded rephrase of one phonetically ambiguous sentence "
        "after independent original-audio ASR failure; must re-run full QA."
    )
    validate_episode(ep)
    validate_catalog(candidate)
    return candidate


def main(base):
    base = Path(base)
    reports = list(base.glob("*/voice_qa.json"))
    if len(reports) != 1:
        print("REPAIR_SKIPPED: no uniquely identified failed QA artifact", flush=True)
        return 0
    voice_file = reports[0]
    ep_id = voice_file.parent.name
    mixed_file = voice_file.with_name("mixed_audio_qa.json")
    if not mixed_file.is_file():
        print("REPAIR_SKIPPED: mixed ASR report missing", flush=True)
        return 0
    voice = json.loads(voice_file.read_text(encoding="utf8"))
    mixed = json.loads(mixed_file.read_text(encoding="utf8"))
    if ledger.api("buffer-publication-receipts/" + ep_id + ".json") or ledger.api(
        "publication-receipts/" + ep_id + ".json"):
        print("REPAIR_SKIPPED: already queued or published; never retry", flush=True)
        return 0
    ref = ledger.api(ledger.item_path(ep_id))
    if ref is None:
        print("REPAIR_SKIPPED: no ledger receipt", flush=True)
        return 0
    receipt = ledger.decode_receipt(ref)
    failed_id = str(os.getenv("FAILED_PREVIEW_RUN_ID", ""))
    if receipt.get("run_id") != failed_id or not failed_id.isdigit():
        print("REPAIR_SKIPPED: outdated or mismatched render attempt", flush=True)
        return 0
    repo_run = github("GET", "actions/runs/" + failed_id)
    if repo_run.get("status") != "completed" or repo_run.get("conclusion") != "failure":
        print("REPAIR_SKIPPED: prior run not provably failed", flush=True)
        return 0
    source = github("GET", "contents/" + CATALOG + "?ref=main")
    old = json.loads(base64.b64decode(source["content"]))
    candidate = repair_episode(old, ep_id, voice, mixed, receipt)
    if candidate is None:
        print("REPAIR_NEEDS_REVIEW: no safe semantic-preserving rephrase available")
        return 0
    value = base64.b64encode((json.dumps(candidate, ensure_ascii=False, indent=2)
                              + "\n").encode("utf8")).decode("ascii")
    github("PUT", "contents/" + CATALOG, {
        "branch":"main", "sha":source["sha"], "content":value,
        "message":"Auto-repair one mispronounced Russian phrase in unreleased " + ep_id,
    })
    # Never count a script revision as a successful audio fix. Re-render and
    # independently QA the changed audio before any Buffer API write.
    github("POST", "actions/workflows/daily-preview.yml/dispatches",
           {"ref":"main"})
    print("REPAIR_RERENDER_REQUESTED", ep_id, "new_qa_required", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "staged"))
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print("REPAIR_FAILED_CLOSED", type(exc).__name__, str(exc)[:180], file=sys.stderr)
        raise SystemExit(1)
