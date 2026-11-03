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
from voice_qa import tokens, match_ratio
from difflib import SequenceMatcher
from autofill_catalog import github

CATALOG = "cloud-shorts/episodes.json"
MAX_REVISION_ATTEMPTS = 3
SAFE_REWRITES = (
    # A frequent Russian voice fusion in ACTUAL owner Cartoon B: expected
    # "На другом видео райдер" was recognized as "На другом видеорайдер".
    # Rephrase the SOURCE action, never copy the fused fake ASR word.
    ("на другом видео", "во втором кадре"),
    # Owner Cartoon B often pronounces unstressed vowels like an English O.
    # Rephrase a physically visible jump without copying a wrong ASR word.
    ("прыгает с трамплина", "совершает прыжок"),
    ("с осмотра", "с простой проверки"),
    ("на мотоцикле", "на байке"),
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
    expected_tokens, heard_tokens = tokens(expected), tokens(heard)
    if match_ratio(expected_tokens, heard_tokens) < .60:
        return None  # Incomplete ASR transcription is not evidence of a bad phrase.
    mismatched = set()
    for tag, before, after, _heard_start, _heard_end in SequenceMatcher(
            None, expected_tokens, heard_tokens, autojunk=False).get_opcodes():
        if tag != "equal":
            mismatched.update(range(before, after))
    for old, new in SAFE_REWRITES:
        if old not in expected.casefold():
            continue
        for occurrence in re.finditer(re.escape(old), expected, flags=re.I):
            token_start = len(tokens(expected[:occurrence.start()]))
            n = len(tokens(old))
            if not mismatched.intersection(range(token_start, token_start + n)):
                continue  # Another occurrence may have been spoken correctly.
            def preserve_capital(match):
                return new[0].upper() + new[1:] if match.group(0)[0].isupper() else new
            updated = expected[:occurrence.start()] + preserve_capital(occurrence) + expected[occurrence.end():]
            if updated != expected and 25 <= len(updated) <= MAX_LEN:
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
    if count < 1:
        return None
    # Third-party/historic repair keeps its legacy bounded retry policy.
    # Owner-authored Cartoon B originals use evidence-backed progress instead
    # of an arbitrary numeric ceiling (each new phrase must be truly distinct).
    if voice_qa.get("episode_id") != ep_id or mixed_qa.get("episode_id") != ep_id:
        return None
    if voice_qa.get("passed") is True and mixed_qa.get("passed") is True:
        return None
    episodes = catalog.get("episodes", [])
    old = next((x for x in episodes if x["id"] == ep_id), None)
    if old and old.get("auto_publish") is False and old.get("voice_engine") == "gustava_selfhosted_qwen3":
        # A single unattended private Cartoon B rephrase after a genuine
        # raw+mixed ASR mismatch. No false positive on previously sent posts
        # or unknown footage; no threshold weakening or voice replacement.
        from selfhosted_voice import CARTOON_B_REFERENCE_SHA, CARTOON_B_PROFILE_ID
        from moto_assets import source_id
        from source_story import require_filmable
        # An already rewritten private episode may be repaired AGAIN only
        # after its distinct second MP4 was really rendered and its own new
        # raw+mixed ASR independently failed. Never retry the same fingerprint.
        old_fingerprint = ledger.preview_fingerprint(old)
        old_proof = old.get("voice_revision_evidence") or {}
        old_history = list(old.get("voice_revision_hash_history") or [])
        if count > 1:
            old_hash = __import__("hashlib").sha256(
                old["narration"].encode("utf8")).hexdigest()
            if (old.get("voice_revision_requested") is not True
                    or not isinstance(old_proof,dict)
                    or old_proof.get("new_narration_sha256") != old_hash
                    or old_proof.get("prior_run_id") != str(receipt.get("previous_run_id"))
                    or old_proof.get("original_voice_reference_sha256") != CARTOON_B_REFERENCE_SHA
                    or not re.fullmatch(r"[0-9a-f]{64}",str(old_proof.get("old_narration_sha256") or ""))):
                return None
            old_history.extend([old_proof["old_narration_sha256"],old_hash])
        if (receipt.get("preview_fingerprint") != old_fingerprint
                or old.get("voice_profile") != CARTOON_B_PROFILE_ID
                or old.get("selfhosted_voice_id") != "gustava-cartoon-b-v1"
                or voice_qa.get("voice_profile") != CARTOON_B_PROFILE_ID
                or voice_qa.get("selfhosted_reference_sha256") != CARTOON_B_REFERENCE_SHA
                or voice_qa.get("voice_speaker") != "gustava-cartoon-b-v1"
                or voice_qa.get("passed") is not False
                # A genuine failed original voice may coexist with a 100%
                # FINAL mixed MP4 ASR. Mixing cannot fix fused source words.
                # Rerender a distinct accurate spoken phrase instead of
                # wasting three mix-gain retries and blocking forever.
                or type(mixed_qa.get("passed")) is not bool
                or mixed_qa.get("source") != "FINAL_MIXED_MP4"
                or not .90 <= float(voice_qa.get("lexical_coverage") or 0) < .97
                or not .90 <= float(mixed_qa.get("lexical_coverage") or 0) <= 1.0
                or receipt.get("voice_qa_passed") is not False
                or receipt.get("mixed_audio_qa_passed") is not mixed_qa.get("passed")
                or not re.fullmatch(r"[0-9a-f]{64}",str(mixed_qa.get("mp4_sha256") or ""))
                or not re.fullmatch(r"[0-9a-f]{64}",str(receipt.get("preview_fingerprint") or ""))
                or not str(receipt.get("run_id") or "").isdigit()
                or not (len(old.get("footage") or []) == 2 and
                        all(source_id(f).startswith("gustava-original-")
                            for f in old["footage"]))):
            return None
        fresh = simple_rewrite(old["narration"],str(voice_qa.get("recognized_text") or ""))
        if not fresh or not 125<=len(fresh)<=300:
            return None
        sha256 = __import__("hashlib").sha256
        old_hash = sha256(old["narration"].encode("utf8")).hexdigest()
        fresh_hash = sha256(fresh.encode("utf8")).hexdigest()
        if fresh_hash in set(old_history) or fresh_hash == old_hash:
            # No cycling through same two phrases merely to evade the
            # previous failed run, regardless of attempt number.
            return None
        sources=old["footage"]
        require_filmable({"narration":fresh},sources)
        candidate=copy.deepcopy(catalog)
        ep=next(x for x in candidate["episodes"] if x["id"] == ep_id)
        ep["narration"]=fresh
        ep["voice_revision_requested"]=True
        ep["voice_revision_priority"]=True
        ep["voice_revision_reason"]="private_original_cartoon_b_phonetic_rephrase"
        ep["voice_revision_hash_history"]=list(dict.fromkeys(
            old_history + [old_hash, fresh_hash]))
        ep["voice_revision_evidence"]={
            "prior_run_id":str(receipt["run_id"]),
            "prior_preview_fingerprint":receipt["preview_fingerprint"],
            "prior_mp4_sha256":mixed_qa["mp4_sha256"],
            "old_narration_sha256":__import__("hashlib").sha256(
                old["narration"].encode("utf8")).hexdigest(),
            "new_narration_sha256":__import__("hashlib").sha256(
                fresh.encode("utf8")).hexdigest(),
            "immutable_source_ids":[source_id(s) for s in sources],
            "original_voice_reference_sha256":CARTOON_B_REFERENCE_SHA,
            "raw_coverage":float(voice_qa["lexical_coverage"]),
            "mixed_coverage":float(mixed_qa["lexical_coverage"]),
            "prior_mixed_qa_passed":mixed_qa["passed"],
            "prior_attempt_count":count,
            "policy":"distinct_phonetic_progress_only",
        }
        validate_episode(ep)
        validate_catalog(candidate)
        return candidate
    if not old or old.get("auto_publish") is not True or old.get("voice_engine") != "kokoro_ru_dima":
        return None
    if count >= MAX_REVISION_ATTEMPTS:
        return None  # Historic third-party Kokoro limit is unchanged.
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
    technical = list(base.glob("*/repair_history.json"))
    diagnostic = (json.loads(technical[0].read_text(encoding="utf8"))
                  if len(technical) == 1 else {})
    errors = diagnostic.get("attempts") or []
    technical_source_failure = bool(
        errors and errors[-1].get("status") == "technical_error"
        and errors[-1].get("source_failure") is True
    )
    if technical_source_failure:
        ep_id = technical[0].parent.name
        diag = diagnostic
        mode = "source"
    elif len(reports) == 1:
        ep_id = reports[0].parent.name
        mixed_file = reports[0].with_name("mixed_audio_qa.json")
        if not mixed_file.is_file():
            print("REPAIR_SKIPPED: mixed ASR report missing", flush=True)
            return 0
        raw = json.loads(reports[0].read_text(encoding="utf8"))
        mix = json.loads(mixed_file.read_text(encoding="utf8"))
        mode = "voice"
    else:
        print("REPAIR_SKIPPED: no single verifiable failure artifact", flush=True)
        return 0

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
    if mode == "voice":
        candidate = repair_episode(old, ep_id, raw, mix, receipt)
        message = "Auto-repair one mispronounced Russian phrase in unreleased " + ep_id
    else:
        from source_repair import episode_theme, discover_new_sources, source_repair
        ep = next((x for x in old["episodes"] if x["id"] == ep_id), None)
        theme = episode_theme(ep) if ep else None
        if not theme:
            print("SOURCE_REPAIR_BLOCKED: no exact motorcycle topic", flush=True)
            return 0
        history_ref = ledger.api(ledger.HISTORY_PATH)
        history = ledger.decode_history(history_ref)  # mandatory permanent anti-reuse
        permanently_used = set(history["used"])
        new_media = discover_new_sources(theme, permanently_used,
                                          os.getenv("PEXELS_API_KEY", ""))
        candidate = source_repair(old, ep_id, receipt, diag, new_media,
                                  permanently_used=permanently_used)
        message = "Auto-replace broken licensed motorcycle footage in unpublished " + ep_id
    if candidate is None:
        print("REPAIR_NEEDS_REVIEW: no safe licensed or semantic-preserving repair available")
        return 0
    value = base64.b64encode((json.dumps(candidate, ensure_ascii=False, indent=2)
                              + "\n").encode("utf8")).decode("ascii")
    github("PUT", "contents/" + CATALOG, {
        "branch": "main", "sha": source["sha"], "content": value,
        "message": message,
    })
    # This is NOT publication: the changed source/text receives a fresh
    # independent render, narration ASR, final mixed audio and motion QA.
    github("POST", "actions/workflows/daily-preview.yml/dispatches",
           {"ref": "main"})
    print("REPAIR_RERENDER_REQUESTED", ep_id, mode, flush=True)
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "staged"))
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print("REPAIR_FAILED_CLOSED", type(exc).__name__, str(exc)[:180], file=sys.stderr)
        raise SystemExit(1)
