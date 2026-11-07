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

from apply_exact_qa_episode_repair import change as apply_verified_episode_revision
from editorial_guard import source_id, validate_catalog
from editorial_novelty import is_repeated_visual_formula
from visual_director import verify_story_subject
from deep_voice import (PROFILE_ID as REQUIRED_MALE_PROFILE,
                        VOICE_ENGINE as REQUIRED_MALE_ENGINE,
                        ready as deep_audio_ready)
from voice_routing import ready as voice_ready


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


def may_enter_preview_queue(episode):
    """An editorially rejected preview stays blocked until a new reviewed fix."""
    return (episode.get("auto_preview") is True
            and episode.get("editorial_rejected") is not True
            and episode.get("visual_review_failed") is not True)


def pick(episodes, exists):
    """Pure helper: select first eligible, never-reserved item."""
    for ep in episodes:
        if may_enter_preview_queue(ep) and not exists(ep["id"]):
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
    "selfhosted_voice.py", "voice_routing.py", "visual_director.py",
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


def eligible_private_original_cartoon_b_asr_retry(episode, receipt, new_fingerprint):
    """At most one SHA-pinned PRIVATE text correction from a truly failed QA.

    The original written narration has one misheard nonword; the repair bot
    rewrites it to a simple, equivalent action phrase, preserves both exact
    original video source SHAs and the verified owner Cartoon B reference.
    This is never a Buffer publishing operation.
    """
    if (not isinstance(receipt,dict) or receipt.get("id") != episode.get("id")
            or receipt.get("state") != "preview_ready"
            or type(receipt.get("attempt_count")) is not int
            or receipt["attempt_count"] < 1
            or receipt.get("voice_qa_passed") is not False
            or type(receipt.get("mixed_audio_qa_passed")) is not bool
            or episode.get("auto_preview") is not True
            or episode.get("auto_publish") is not False
            or episode.get("voice_engine") != "gustava_selfhosted_qwen3"
            or episode.get("selfhosted_voice_id") != "gustava-cartoon-b-v1"
            or episode.get("voice_revision_requested") is not True
            or episode.get("voice_revision_reason")
               != "private_original_cartoon_b_phonetic_rephrase"):
        return False
    proof = episode.get("voice_revision_evidence")
    if not isinstance(proof,dict):
        return False
    from selfhosted_voice import CARTOON_B_REFERENCE_SHA, CARTOON_B_PROFILE_ID
    if (episode.get("voice_profile") != CARTOON_B_PROFILE_ID
            or receipt.get("selfhosted_reference_sha256") != CARTOON_B_REFERENCE_SHA
            or proof.get("original_voice_reference_sha256") != CARTOON_B_REFERENCE_SHA
            or proof.get("prior_run_id") != str(receipt.get("run_id"))
            or proof.get("prior_preview_fingerprint") != receipt.get("preview_fingerprint")
            or proof.get("policy") != "distinct_phonetic_progress_only"
            or proof.get("prior_attempt_count") != receipt["attempt_count"]
            or not re.fullmatch(r"[a-f0-9]{64}",str(proof.get("prior_mp4_sha256") or ""))
            or not re.fullmatch(r"[a-f0-9]{64}",str(proof.get("old_narration_sha256") or ""))
            or proof.get("new_narration_sha256") !=
               hashlib.sha256(str(episode.get("narration") or "").encode("utf8")).hexdigest()
            or not .90<=float(proof.get("raw_coverage") or 0)<.97
            or not .90<=float(proof.get("mixed_coverage") or 0)<=1.0
            or proof.get("prior_mixed_qa_passed") is not
               receipt.get("mixed_audio_qa_passed")
            or receipt.get("preview_fingerprint") == new_fingerprint):
        return False
    history = episode.get("voice_revision_hash_history") or []
    if (not isinstance(history,list) or len(history)<2
            or len(history)!=len(set(history))
            or not all(re.fullmatch(r"[a-f0-9]{64}",str(x)) for x in history)
            or history[-2] != proof.get("old_narration_sha256")
            or history[-1] != proof.get("new_narration_sha256")):
        return False
    footage = episode.get("footage") or []
    try:
        if (len(footage)!=2
                or not all(source_id(s).startswith("gustava-original-") for s in footage)
                or [source_id(s) for s in footage]!=proof.get("immutable_source_ids")):
            return False
        from source_story import require_filmable
        narration=episode.get("narration")
        if not isinstance(narration,str) or not 125<=len(narration)<=300:
            return False
        require_filmable({"narration":narration},footage)
    except (ValueError,TypeError,KeyError):
        return False
    return True


def eligible_independently_rejected_scene_repair(episode, receipt, new_fingerprint):
    """A genuinely reviewed, unpublished first-scene replacement is rerenderable.

    This guard NEVER approves a release. The exact previous six-frame
    rejection must also be independently fetched from the immutable render
    ledger in choose() before a new reservation is written.
    """
    if not (isinstance(receipt,dict)
            and receipt.get("id")==episode.get("id")
            and receipt.get("state")=="preview_ready"
            and receipt.get("attempt_count")==1
            and receipt.get("voice_qa_passed") is True
            and receipt.get("mixed_audio_qa_passed") is True
            and receipt.get("male_voice_verified") is True
            and episode.get("auto_preview") is True
            and episode.get("auto_publish") is False
            and episode.get("visual_revision_requested") is True
            and episode.get("visual_revision_reason")==
                "independent_frame_review_rejected_first_source_action"
            and episode.get("voice_engine")==REQUIRED_MALE_ENGINE
            and episode.get("voice_profile")==receipt.get("voice_profile")
            and new_fingerprint!=receipt.get("preview_fingerprint")):
        return False
    proof=episode.get("visual_revision_evidence") or {}
    sources=episode.get("footage") or []
    audio=episode.get("deep_audio") or {}
    if (not isinstance(proof,dict) or len(sources)!=2
            or proof.get("prior_run_id")!=str(receipt.get("run_id"))
            or proof.get("prior_preview_fingerprint")!=receipt.get("preview_fingerprint")
            or proof.get("prior_deep_audio_sha256")!=receipt.get("deep_source_sha256")
            or audio.get("source_audio_sha256")!=receipt.get("deep_source_sha256")
            or not re.fullmatch(r"[0-9a-f]{64}",str(proof.get("prior_mp4_sha256") or ""))
            or not re.fullmatch(r"[0-9a-f]{40}",str(proof.get("rejection_receipt_blob_sha") or ""))
            or proof.get("previous_review_status")!="needs_new_verified_visuals"
            or proof.get("rejection_reason")!="FRAME_MODEL_REJECTED_ACTION_OR_NARRATION"
            or proof.get("unpublished_only") is not True
            or proof.get("immutable_narration") is not True
            or proof.get("max_total_attempts")!=2):
        return False
    from editorial_guard import source_id
    from native_source_preflight import source_proof
    from source_action_evidence import source_dynamic_action_verified
    from source_story import scene_for
    try:
        first,second=sources
        if (source_id(first)!=proof.get("replacement_source_id")
                or source_id(second)!=proof.get("unchanged_second_source_id")
                or source_id(first)==proof.get("prior_source_id")
                or first.get("native_4k_sha256")!=proof.get("replacement_source_sha256")
                or not source_dynamic_action_verified(first)
                or not source_dynamic_action_verified(second)
                or scene_for(first)[0]!="ride"
                or scene_for(second)[0]!="jump"):
            return False
        source_proof(first,"2k")
        source_proof(second,"2k")
    except (ValueError,TypeError,IndexError,KeyError):
        return False
    return True


def independently_verified_rejection_receipt(episode, receipt, get=api):
    """Cross-check owner/GitHub rejection, never trust a catalog self-report."""
    if not (episode.get("visual_revision_reason")==
            "independent_frame_review_rejected_first_source_action"):
        return True
    if not isinstance(receipt,dict):
        return False
    proof=episode.get("visual_revision_evidence") or {}
    run=str(receipt.get("run_id") or "")
    if not re.fullmatch(r"[0-9]{8,16}",run):
        return False
    path=("automation/visual-review-rejections/"+episode["id"]+
          "-"+run+".json")
    entry=get(path)
    if (not isinstance(entry,dict)
            or entry.get("sha")!=proof.get("rejection_receipt_blob_sha")
            or not isinstance(entry.get("content"),str)):
        return False
    try:
        record=json.loads(base64.b64decode(
            "".join(entry["content"].split()),validate=True))
    except (ValueError,TypeError,KeyError,binascii.Error):
        return False
    return bool(record.get("episode")==episode["id"]
                and str(record.get("run_id"))==run
                and record.get("status")=="needs_new_verified_visuals"
                and record.get("reason")=="FRAME_MODEL_REJECTED_ACTION_OR_NARRATION")


def eligible_retry(episode, receipt, new_fingerprint):
    """Rerender only a genuinely revised, never-published failed preview."""
    if receipt is None or receipt.get("id") != episode["id"]:
        return False
    if receipt.get("state") != "preview_ready":
        return False
    if episode.get("voice_revision_reason") == "private_original_cartoon_b_phonetic_rephrase":
        return eligible_private_original_cartoon_b_asr_retry(
            episode, receipt, new_fingerprint)
    attempts = int(receipt.get("attempt_count", 1))
    # Exact earlier preview: at 3.900s the mud caption appeared while
    # 5.881s of racing video remained. A successful private QA pass did not
    # imply audio / visual storytelling alignment. Require a documented,
    # SHA-pinned review of the *previous* MP4 before a single visual retry.
    scene_proof = episode.get("visual_revision_evidence") or {}
    scene_retime = (
        episode.get("visual_revision_reason") == "spoken_scene_caption_mismatch"
        and episode.get("auto_publish") is False
        and isinstance(scene_proof, dict)
        and scene_proof.get("prior_run_id") == str(receipt.get("run_id"))
        and bool(re.fullmatch(r"[0-9a-f]{64}",
                              str(scene_proof.get("prior_mp4_sha256") or "")))
        and type(scene_proof.get("old_caption_start_seconds")) in (float, int)
        and type(scene_proof.get("old_second_scene_start_seconds")) in (float, int)
        and (scene_proof["old_second_scene_start_seconds"]
             - scene_proof["old_caption_start_seconds"] >= .70)
    )
    # One SHA-and-ledger-bound PRIVATE correction after inspecting the actual
    # frame sequence. The first 5.905s showed trees, not the narrated rider;
    # the replacement source visibly shows motocross at 0.6s and 4.2s.
    # No arbitrary successful preview may be retried on metadata alone.
    scene_source_repair = (
        episode.get("id") == "moto-motocross-223d9ab5c67d"
        and episode.get("auto_preview") is True
        and episode.get("auto_publish") is False
        and episode.get("visual_revision_reason")
            == "actual_first_shot_missing_moto_action"
        and episode.get("voice_engine") == "gustava_selfhosted_qwen3"
        and attempts == 1
        and str(receipt.get("run_id")) == "41370745453"
        and receipt.get("preview_fingerprint")
            == "b371f99d486f19f3b38ab630522ac5677d876f950fc16a106e0d59c9f49a4ba4"
        and receipt.get("voice_qa_passed") is True
        and receipt.get("mixed_audio_qa_passed") is True
        and isinstance(scene_proof, dict)
        and scene_proof.get("prior_run_id") == "41370745453"
        and scene_proof.get("prior_mp4_sha256")
            == "1726369965ae387dbb70bbc036c61fcba7fd3dc84de528e3456aac53fb8488e5"
        and scene_proof.get("prior_preview_fingerprint")
            == receipt.get("preview_fingerprint")
        and scene_proof.get("prior_source_id") == "12990227"
        and scene_proof.get("replacement_source_id") == "32399067"
        and len(episode.get("footage") or []) == 2
        and [source_id(f) for f in episode["footage"]]
            == ["32399067", "9607287"]
        and [f.get("author") for f in episode["footage"]]
            == ["Harvey Tan Villarino", "Anastasia Shuraeva"]
        and episode["footage"][0].get("license") == "Pexels License"
        and episode.get("shots", [{}])[0].get("seconds") == 6.82
    )
    # Never downgrade an evidence-backed visual correction into a generic
    # failed-audio retry if any part of its proof fails.
    if (episode.get("visual_revision_reason")
            == "actual_first_shot_missing_moto_action"
            and not scene_source_repair):
        return False
    # Single SHA-pinned PRIVATE rewording after listening/independent ASR
    # documented a real word fusion: «видеомеханик» instead of two words.
    # Never reuse a public MP4, change sources, swap voice, or claim approval.
    word_proof = episode.get("voice_revision_evidence") or {}
    private_fused_word_repair = (
        episode.get("id") == "moto-city-3a2aad34e115"
        and episode.get("auto_preview") is True
        and episode.get("auto_publish") is False
        and episode.get("voice_engine") == "gustava_selfhosted_qwen3"
        and episode.get("voice_profile") == "gustava_original_qwen3_v1"
        and episode.get("selfhosted_voice_id") == "gustava-original-v1"
        and episode.get("voice_revision_requested") is True
        and episode.get("voice_revision_reason")
            == "raw_and_final_asr_fused_video_mechanic"
        and attempts == 1
        and str(receipt.get("run_id")) == "41373650226"
        and receipt.get("preview_fingerprint")
            == "8ea4ff16627b5ef49c0a154f490d70214c351400986aabfb715c603e4cd43811"
        and receipt.get("voice_profile") == episode.get("voice_profile")
        and receipt.get("selfhosted_reference_sha256")
            == "ed27b23b9f86345c45263ab28957e96fd2d399379b3ea90ed9fbc75be183a3cc"
        and receipt.get("voice_qa_passed") is False
        and receipt.get("mixed_audio_qa_passed") is False
        and isinstance(word_proof, dict)
        and word_proof.get("prior_run_id") == "41373650226"
        and word_proof.get("prior_mp4_sha256")
            == "cf3c18ae89f5d1dd8b37b009ea923dffae542bb40a2ff16dfaef162b50a5691c"
        and word_proof.get("prior_preview_fingerprint")
            == receipt.get("preview_fingerprint")
        and word_proof.get("raw_coverage") == 0.913
        and word_proof.get("mixed_coverage") == 0.913
        and word_proof.get("expected_phrase") == "На другом видео механик"
        and word_proof.get("recognized_phrase") == "На другом видеомеханик"
        and word_proof.get("immutable_source_ids") == ["35963831", "mixkit-41937"]
        and word_proof.get("independent_voice_reference_sha256")
            == receipt.get("selfhosted_reference_sha256")
        and word_proof.get("editorial_remains_private") is True
        and word_proof.get("max_total_preview_attempts") == 2
        and len(episode.get("footage") or []) == 2
        and [source_id(x) for x in episode["footage"]]
            == ["35963831", "mixkit-41937"]
        and episode.get("narration")
            == "Мотоцикл в двух сценах: байкер едет по городской улице. Вторая сцена: механик меняет масло в мотоцикле. Это независимые съёмки. Что ближе тебе?"
        and 125 <= len(episode.get("narration", "")) <= 160
    )
    if (episode.get("voice_revision_reason")
            == "raw_and_final_asr_fused_video_mechanic"
            and not private_fused_word_repair):
        return False
    # Exact real-MP4 proof for this PRIVATE content/timing correction.
    # The prior passed audio QA but the "oil change" label appeared 2.545s
    # before the real switch from moving city traffic to motor-oil footage.
    city_caption_proof = episode.get("visual_revision_evidence") or {}
    city_caption_repair = (
        episode.get("id") == "moto-city-3a2aad34e115"
        and episode.get("visual_revision_reason") == "spoken_scene_caption_mismatch"
        and episode.get("visual_revision_requested") is True
        and episode.get("auto_preview") is True
        and episode.get("auto_publish") is False
        and episode.get("align_middle_caption_to_second_scene") is True
        and episode.get("voice_engine") == "gustava_selfhosted_qwen3"
        and episode.get("voice_profile") == "gustava_original_qwen3_v1"
        and episode.get("selfhosted_voice_id") == "gustava-original-v1"
        and attempts == 2
        and str(receipt.get("run_id")) == "41374584510"
        and receipt.get("preview_fingerprint")
            == "730b9c9054aacca1f6d789d7704e9d655292e49cdef68a2d8a36ad20fc374faa"
        and receipt.get("voice_qa_passed") is True
        and receipt.get("mixed_audio_qa_passed") is True
        and receipt.get("voice_profile") == episode.get("voice_profile")
        and receipt.get("selfhosted_reference_sha256")
            == "ed27b23b9f86345c45263ab28957e96fd2d399379b3ea90ed9fbc75be183a3cc"
        and isinstance(city_caption_proof, dict)
        and city_caption_proof.get("prior_run_id") == "41374584510"
        and city_caption_proof.get("prior_mp4_sha256")
            == "d4773cab50f7eb67c8ab598b712fa70cac2b03bcf58ff677c3cdfac86a9362a7"
        and city_caption_proof.get("prior_preview_fingerprint")
            == receipt.get("preview_fingerprint")
        and city_caption_proof.get("old_caption_start_seconds") == 3.9
        and city_caption_proof.get("old_second_scene_start_seconds") == 6.445
        and city_caption_proof.get("old_second_scene_start_source_duration_seconds") == 6.545
        and city_caption_proof.get("opening_trim_seconds") == .1
        and city_caption_proof.get("old_caption_early_by_seconds") == 2.545
        and city_caption_proof.get("source_ids") == ["35963831","mixkit-41937"]
        and city_caption_proof.get("previous_voice_qa_passed") is True
        and city_caption_proof.get("previous_final_mix_qa_passed") is True
        and city_caption_proof.get("source_licenses_unchanged") is True
        and city_caption_proof.get("never_publish_on_visual_retry") is True
        and city_caption_proof.get("max_total_attempts") == 3
        and len(episode.get("footage") or []) == 2
        and [source_id(x) for x in episode["footage"]]
            == ["35963831","mixkit-41937"]
    )
    if (episode.get("id") == "moto-city-3a2aad34e115"
            and episode.get("visual_revision_reason") == "spoken_scene_caption_mismatch"
            and not city_caption_repair):
        return False
    independent_scene_repair=eligible_independently_rejected_scene_repair(
        episode,receipt,new_fingerprint)
    if (episode.get("visual_revision_reason")==
            "independent_frame_review_rejected_first_source_action"
            and not independent_scene_repair):
        return False
    visual_repair = (episode.get("visual_revision_requested") is True
                     and (independent_scene_repair or scene_source_repair
                     or episode.get("visual_revision_reason") in (
                         "source_freeze_confirmed",
                         "owner_rejected_static_helmet_coverage",
                         "owner_rejected_end_clip_no_helmet_removal",
                         "caption_clipped_confirmed")
                         or scene_retime))
    male_voice_repair = (
        episode.get("voice_engine") == REQUIRED_MALE_ENGINE
        and episode.get("voice_revision_requested") is True
        and episode.get("voice_profile") == REQUIRED_MALE_PROFILE
        and receipt.get("voice_profile") != REQUIRED_MALE_PROFILE
    )
    # One evidence-backed private-only recovery after a failed FINAL mixed
    # audio ASR and editorial frame review. The original WAV passed: 1.000.
    # This is specific to the exact third-render MP4, with 3 -> 4 as the
    # absolute limit, never public upload or an unverified new source.
    audio_proof = episode.get("mixed_editorial_revision_evidence") or {}
    verified_mix_editorial_repair = (
        episode.get("id") == "moto-roadtrip-5b98825cae72"
        and episode.get("auto_preview") is True
        and episode.get("auto_publish") is False
        and episode.get("voice_engine") == "gustava_selfhosted_qwen3"
        and episode.get("voice_profile") == "gustava_original_qwen3_v1"
        and episode.get("mixed_editorial_revision_requested") is True
        and episode.get("mixed_editorial_revision_reason")
            == "actual_final_mix_asr_and_visual_truth_fix"
        and receipt.get("voice_qa_passed") is True
        and receipt.get("mixed_audio_qa_passed") is False
        and receipt.get("voice_profile") == episode.get("voice_profile")
        and str(receipt.get("run_id")) == "41333288738"
        and attempts == MAX_ATTEMPTS
        and isinstance(audio_proof, dict)
        and audio_proof.get("prior_run_id") == "41333288738"
        and audio_proof.get("prior_mp4_sha256")
            == "68ed361b2d2b6936cfe224eb7072b3896b2c005b205f8c349bef487038191b86"
        and audio_proof.get("prior_raw_asr_coverage") == 1.0
        and audio_proof.get("prior_mixed_asr_coverage") == 0.957
        and audio_proof.get("source_ids") == ["32659157", "31894372"]
        and episode.get("clean_speech_intro_seconds") == 3.3
        and "по треку" in episode.get("narration", "").casefold()
        and "путешеств" in episode.get("narration", "").casefold()
        and "гонка" not in episode.get("narration", "").casefold()
        and 125 <= len(episode.get("narration", "")) <= 160
        and {source_id(f) for f in episode.get("footage", [])}
            == {"32659157", "31894372"}
    )
    limit = (MAX_DOCUMENTARY_ATTEMPTS if
             episode.get("episode_series", {}).get("historical_reconstruction")
             else MAX_VISUAL_REPAIR_ATTEMPTS
             if visual_repair or male_voice_repair or verified_mix_editorial_repair or private_fused_word_repair else MAX_ATTEMPTS)
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
        if (not any(u.endswith("-" + new_media) or u.endswith("/" + new_media) for u in sources)
                or any(u.endswith("-" + old_media) or u.endswith("/" + old_media) for u in sources)):
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


def eligible_abandoned_owner_phonetic_retry(episode, receipt, new_fingerprint,
                                           old_conclusion):
    """One real failed PRIVATE MP4 may be revoiced after an exact ASR word error.

    The prior Qwen recording said `потоки` instead of `потоке` both in raw
    narration and the final MP4. Do not mask a real utterance error by
    relaxing the 97% QA threshold or repeating identical DSP adjustments.
    """
    if (episode.get("id") != "moto-vintage-1211a46b1a90"
            or not isinstance(receipt, dict)
            or receipt.get("state") != "reserved"
            or receipt.get("id") != episode.get("id")
            or receipt.get("run_id") != "42265495571"
            or receipt.get("preview_fingerprint")
               != "41ceab71295cd87ef386492dc42948980fde37da104bd4c7ce7e99d6ada8a796"
            or type(receipt.get("attempt_count")) is not int
            or receipt["attempt_count"] != 1
            or old_conclusion != "failure"
            or episode.get("auto_preview") is not True
            or episode.get("auto_publish") is not False
            or episode.get("voice_engine") != "gustava_selfhosted_qwen3"
            or episode.get("voice_profile") != "gustava_cartoon_b_qwen3_v1"
            or episode.get("selfhosted_voice_id") != "gustava-cartoon-b-v1"
            or episode.get("voice_revision_requested") is not True
            or episode.get("voice_revision_reason")
               != "verified_failed_private_qwen_phonetic_rephrase"
            or new_fingerprint == receipt.get("preview_fingerprint")):
        return False
    proof = episode.get("voice_revision_evidence")
    if not isinstance(proof, dict):
        return False
    original = (
        "Мотоцикл: сначала байкер едет по городской улице. "
        "В другом кадре райдер проезжает грязный участок. "
        "В грязи и потоке машин риски разные — смотри вперёд.")
    improved = (
        "Мотоцикл: сначала байкер едет по городской улице. "
        "В другом кадре райдер проезжает грязный участок. "
        "В городе следи за машинами, а в грязи действуй плавно.")
    sources = episode.get("footage") or []
    if (episode.get("narration") != improved
            or not 125 <= len(improved) <= 160
            or proof.get("old_narration_sha256") !=
               hashlib.sha256(original.encode("utf8")).hexdigest()
            or proof.get("new_narration_sha256") !=
               hashlib.sha256(improved.encode("utf8")).hexdigest()
            or proof.get("failed_run_id") != receipt["run_id"]
            or proof.get("failed_preview_fingerprint") != receipt["preview_fingerprint"]
            or proof.get("raw_asr_coverage") != .957
            or proof.get("mixed_asr_coverage") != .957
            or proof.get("expected_word") != "потоке"
            or proof.get("heard_word") != "потоки"
            or proof.get("prior_artifact_id") != 13525589657
            or proof.get("public_upload_permitted") is not False
            or proof.get("max_total_preview_attempts") != 2
            or len(sources) != 2):
        return False
    try:
        if proof.get("unchanged_source_ids") != [source_id(x) for x in sources]:
            return False
        from source_story import require_filmable
        require_filmable({"narration": improved}, sources)
        from selfhosted_voice import CARTOON_B_REFERENCE_SHA
        if proof.get("narrator_reference_sha256") != CARTOON_B_REFERENCE_SHA:
            return False
    except (KeyError, TypeError, ValueError):
        return False
    return True


def eligible_private_qwen_concise_retry(episode, receipt, new_fingerprint, old_conclusion):
    """Exactly one PRIVATE retry after original speech exceeded real shot caps.

    A previously failed Action run, prior fingerprint and immutable source
    identities are mandatory. No footage reuse by a different episode; no
    external video release. The new text must fit the existing 2-shot
    documentary: both independent actions remain explicitly in narration.
    """
    if (not isinstance(receipt, dict)
            or receipt.get("id") != episode.get("id")
            or receipt.get("state") != "reserved"
            or old_conclusion != "failure"
            or type(receipt.get("attempt_count")) is not int
            or receipt["attempt_count"] != 1
            or episode.get("auto_preview") is not True
            or episode.get("auto_publish") is not False
            or episode.get("voice_engine") != "gustava_selfhosted_qwen3"
            or int(episode.get("visual_director_version") or 0) != 3
            or episode.get("visual_duration_revision_requested") is not True
            or episode.get("visual_duration_revision_reason") !=
                "concise_script_fits_original_moving_scenes"):
        return False
    proof = episode.get("visual_duration_revision_evidence")
    if not isinstance(proof,dict):
        return False
    if (proof.get("previous_run_id") != str(receipt.get("run_id"))
            or proof.get("previous_fingerprint") != receipt.get("preview_fingerprint")
            or proof.get("previous_error") != "VISUAL_DURATION_SHORTAGE"
            or receipt.get("preview_fingerprint") == new_fingerprint):
        return False
    footage=episode.get("footage") or []
    shot_keys={shot.get("source") for shot in episode.get("shots") or []}
    if len(footage)!=2 or len(shot_keys)!=2 or shot_keys!={f.get("key") for f in footage}:
        return False
    try:
        if set(proof.get("source_ids") or []) != {source_id(f) for f in footage}:
            return False
        narration=episode.get("narration")
        if not isinstance(narration,str) or not 125<=len(narration)<=160:
            return False
        from source_story import require_filmable
        require_filmable({"narration":narration},footage)
    except (ValueError,TypeError,KeyError):
        return False
    return True


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


def eligible_verified_native4k_install_retry(episode, receipt, current_fingerprint,
                                            bootstrap_proved):
    """One exact stalled 4K DEEP upload after FFmpeg-install-only failure.

    The previous runner died at optional apt install before render/QA/MP4.
    This code path only accepts same immutable script/source/voice fingerprint
    and exact failed job evidence from GitHub. No blind second publication.
    """
    return bool(
        bootstrap_proved is True
        and episode.get("id") == "moto-native-4k-control-20261106"
        and episode.get("auto_preview") is True
        and episode.get("auto_publish") is False
        and episode.get("voice_engine") == REQUIRED_MALE_ENGINE
        and episode.get("voice_profile") == "gustava_create_audio_deep_v1"
        and episode.get("release_priority") == "first_native_4k_moto_approved"
        and (episode.get("deep_audio") or {}).get("source_audio_sha256")
           == "10624b0af55a9c4804cc622d6ca3e6a585e2d23250489373b94c92ce6be96abf"
        and [source_id(x) for x in (episode.get("footage") or [])]
           == ["5803634","34110751"]
        and isinstance(receipt, dict)
        and receipt.get("state") == "reserved"
        and receipt.get("id") == episode["id"]
        and str(receipt.get("run_id")) == "42272301505"
        and receipt.get("deep_source_sha256")
           == (episode.get("deep_audio") or {}).get("source_audio_sha256")
        and type(receipt.get("attempt_count")) is int
        and receipt.get("attempt_count") == 1
        and receipt.get("preview_fingerprint") == current_fingerprint
    )


def eligible_verified_native4k_frame_repair(episode, receipt, new_fingerprint, rejection):
    """One private rerender of the actual rejected 2K movie, never an upload.

    The image reviewer inspected six frames and rejected video/narration
    agreement. A real new DEEP MP3, source-identical footage and a retimed
    second-scene caption are required, not a changed test flag or a prompt.
    """
    if not (episode.get("id") == "moto-native-4k-control-20261106"
            and episode.get("auto_preview") is True
            and episode.get("auto_publish") is False
            and episode.get("voice_engine") == REQUIRED_MALE_ENGINE
            and episode.get("voice_profile") == "gustava_create_audio_deep_v1"
            and episode.get("voice_revision_requested") is True
            and episode.get("voice_revision_reason") ==
                "verified_frame_model_rejected_prior_abstract_narration"
            and episode.get("align_middle_caption_to_second_scene") is True
            and episode.get("visual_revision_reason") == "spoken_scene_caption_mismatch"
            and episode.get("caption_middle") == "ПРЫЖОК С ТРАМПЛИНА"
            and isinstance(receipt, dict)
            and receipt.get("state") == "preview_ready"
            and receipt.get("id") == episode["id"]
            and receipt.get("run_id") == "42274119556"
            and receipt.get("attempt_count") == 2
            and receipt.get("voice_qa_passed") is True
            and receipt.get("mixed_audio_qa_passed") is True
            and receipt.get("deep_source_sha256") ==
                "10624b0af55a9c4804cc622d6ca3e6a585e2d23250489373b94c92ce6be96abf"
            and receipt.get("preview_fingerprint") != new_fingerprint
            and (episode.get("deep_audio") or {}).get("source_audio_sha256") ==
                "84411b636109859ca471c14c40bdc9e1b3e64e19505c6d660cdb1c8ce2ad4fb1"
            and isinstance(rejection, dict)
            and rejection.get("episode") == episode["id"]
            and rejection.get("run_id") == receipt["run_id"]
            and rejection.get("status") == "needs_new_verified_visuals"
            and rejection.get("reason") == "FRAME_MODEL_REJECTED_ACTION_OR_NARRATION"):
        return False
    evidence = episode.get("visual_revision_evidence") or {}
    voice_evidence = episode.get("voice_revision_evidence") or {}
    footage = episode.get("footage") or []
    return bool(
        evidence.get("prior_run_id") == receipt["run_id"]
        and voice_evidence.get("prior_run_id") == receipt["run_id"]
        and evidence.get("prior_mp4_sha256") ==
            "a8c8658f028defa3feef2279bc0ad05125f1c09165079e8da3df6cb031907ed0"
        and voice_evidence.get("prior_mp4_sha256") == evidence["prior_mp4_sha256"]
        and evidence.get("old_caption_start_seconds") == 3.9
        and evidence.get("old_second_scene_start_seconds") == 7.789
        and voice_evidence.get("prior_deep_audio_sha256") ==
            receipt["deep_source_sha256"]
        and voice_evidence.get("new_deep_audio_sha256") ==
            episode["deep_audio"]["source_audio_sha256"]
        and len(footage) == 2
        and [source_id(x) for x in footage] == ["5803634", "34110751"]
        and [x.get("native_4k_sha256") for x in footage] == [
            "7244d8f3124c77b3f6baa469c43f4ed6f4bf41502a035cd87ddbd5d4e28bdfb9",
            "c2e1d6d4be0e000e9ab36392a522cc931eaa3c62e7179b2afafba9e02c6ab26d",
        ]
    )


# One immutable production incident: the owner's Cartoon B reference was
# missing from the *live* TTS binary when GitHub ran 41422504259. That Action
# exited 403 before any MP4 or Buffer upload; its receipt stayed "reserved".
# The owner subsequently deployed the exact SHA-pinned service on the VPS and
# generated a new 7.76s WAV with independent Russian ASR coverage 1.0.
# Never turn this narrow recovery into a general "retry a reserved job" rule.
OWNER_CARTOON_B_403_RESUME = {
    "id": "moto-training-8b876c464b6c",
    "old_run": "41422504259",
    "old_fingerprint":
        "d5192b33112521a3bf5a186764d737721b7a4914d765bd205f1c70b6da1ae674",
    "source_ids": ("9143349", "30283096"),
    "voice_id": "gustava-cartoon-b-v1",
}


def eligible_verified_cartoon_b_403_resume(episode, receipt, new_fingerprint,
                                          old_conclusion, live_voice_ready):
    """One PRIVATE run after confirmed old 403, with unchanged visual/text fingerprint.

    The live TTS binary was repaired, not the episode or renderer. Requiring
    a changed episode fingerprint would incorrectly strand this exact run.
    The old failed GH run and newly healthy owner endpoint are independent
    evidence; both still have to match, and only attempt_count=1 can enter.
    """
    fixed = OWNER_CARTOON_B_403_RESUME
    if (episode.get("id") != fixed["id"]
            or episode.get("auto_preview") is not True
            or episode.get("auto_publish") is not False
            or episode.get("voice_engine") != "gustava_selfhosted_qwen3"
            or episode.get("selfhosted_voice_id") != fixed["voice_id"]
            or episode.get("editorial_rejected") is True
            or episode.get("visual_review_failed") is True
            or not isinstance(receipt, dict)
            or receipt.get("id") != fixed["id"]
            or receipt.get("run_id") != fixed["old_run"]
            or receipt.get("state") != "reserved"
            or receipt.get("attempt_count") != 1
            or receipt.get("selfhosted_voice_id") != fixed["voice_id"]
            or receipt.get("preview_fingerprint") != fixed["old_fingerprint"]
            or new_fingerprint != fixed["old_fingerprint"]
            or old_conclusion != "failure"
            or live_voice_ready is not True):
        return False
    footage = episode.get("footage")
    if not isinstance(footage, list) or len(footage) != 2:
        return False
    try:
        return tuple(source_id(media) for media in footage) == fixed["source_ids"]
    except (ValueError, TypeError, KeyError):
        return False


def production_cartoon_b_http_ready():
    """Read-only proof that the currently deployed B TTS route is present."""
    req = urllib.request.Request(
        "https://voice.hapychrust.ru/health",
        headers={"Accept": "application/json",
                 "User-Agent": "gustava-verified-private-403-recovery"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            if response.status != 200:
                return False
            state = json.load(response)
        return (state.get("cartoon_b_reference_ready") is True
                and state.get("tts_ready_for_private_request") is True)
    except (OSError, ValueError, TypeError):
        return False


def choose(catalog, output):
    data = json.loads(Path(catalog).read_text(encoding="utf8"))
    apply_verified_episode_revision(data)
    validate_catalog(data)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    listed = []
    native_blocked=0
    require_native=os.environ.get("GUSTAVA_NATIVE_SOURCE_PREFLIGHT")=="1"
    for ep in data["episodes"]:
        if not may_enter_preview_queue(ep) or not voice_ready(ep):
            continue
        if is_repeated_visual_formula(ep, data["episodes"]):
            print("REPETITIVE_VIDEO_BLOCKED", ep["id"], flush=True)
            continue
        try:
            verify_story_subject(ep)
        except ValueError as exc:
            print("VISUAL_STORY_REJECTED_BEFORE_RESERVATION",ep["id"],str(exc)[:300],flush=True)
            continue
        if require_native:
            from native_source_preflight import require_native_sources
            try:
                require_native_sources(
                    ep,os.environ.get("GUSTAVA_EXPORT_PROFILE","2k"))
            except ValueError as exc:
                native_blocked+=1
                if native_blocked<=5:
                    print("NATIVE_2K_SOURCE_NOT_READY_NO_RESERVATION",
                          ep["id"],str(exc),flush=True)
                continue
        listed.append(ep)
    print("GUSTAVA_APPROVED_VOICE_AND_VISUAL_READY_EPISODES",len(listed),
          "native_source_blocked",native_blocked,flush=True)
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
    # Urgent owner-requested genuine 4K debut: previous exact source+voice
    # was reserved but died before any render at FFmpeg apt bootstrap.
    # Do not strand this private untouched clip behind unrelated drafts.
    # GitHub must prove the exact old install step FAILED before retry.
    selected = None
    # A real six-frame independent review rejected the existing 2K movie.
    # Prefer the ONE revised private render before draining unrelated ideas.
    # The rejection proof and render+voice SHA are immutable; no publication
    # attempt may be made by this selector itself.
    for ep in listed:
        if ep.get("id") != "moto-native-4k-control-20261106":
            continue
        _, receipt = records[ep["id"]]
        if (not isinstance(receipt, dict)
                or receipt.get("run_id") != "42274119556"
                or receipt.get("state") != "preview_ready"
                or not unpublished(ep["id"])):
            continue
        reject_file = api(
            "automation/visual-review-rejections/"
            "moto-native-4k-control-20261106-42274119556.json")
        if not reject_file:
            continue
        try:
            rejection = json.loads(base64.b64decode(
                "".join(reject_file["content"].split()), validate=True))
        except (KeyError, TypeError, ValueError, binascii.Error) as exc:
            raise RuntimeError("INVALID_PREVIOUS_FRAME_REJECTION_RECEIPT") from exc
        fingerprint = preview_fingerprint(ep)
        if (eligible_verified_native4k_frame_repair(
                ep, receipt, fingerprint, rejection)
                and eligible_retry(ep, receipt, fingerprint)):
            selected = ep
            print("FIRST_2K_FRAME_REVIEWED_PRIVATE_REVISION",
                  ep["id"], "attempt", receipt["attempt_count"] + 1,
                  flush=True)
            break
    for ep in listed:
        if selected is not None:
            break
        if ep.get("id") != "moto-native-4k-control-20261106":
            continue
        _, receipt = records[ep["id"]]
        if (isinstance(receipt, dict)
                and receipt.get("state") == "reserved"
                and str(receipt.get("run_id")) == "42272301505"
                and receipt.get("attempt_count") == 1
                and unpublished(ep["id"])):
            current_fp = preview_fingerprint(ep)
            if eligible_abandoned_bootstrap_retry(
                    ep, receipt, current_fp,
                    verified_failed_preflight(receipt["run_id"])):
                selected = ep
                print("FIRST_GENUINE_4K_RETRY_GITHUB_VERIFIED",
                      ep["id"],flush=True)
                break
    if selected is None:
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
            # The current catalogue does not grant its own frame-approval:
            # require the exact GitHub rejection blob from the old MP4.
            if (item.get("visual_revision_reason")==
                    "independent_frame_review_rejected_first_source_action"
                    and not independently_verified_rejection_receipt(item,receipt)):
                continue
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
                    or item.get("visual_duration_revision_requested") is True
                    or item.get("voice_revision_requested") is True):
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
                        item, receipt, new_fp, outcome)
                    or eligible_private_qwen_concise_retry(
                        item, receipt, new_fp, outcome)
                    or eligible_abandoned_owner_phonetic_retry(
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
            if (eligible_abandoned_bootstrap_retry(item, receipt, new_fp, proof)
                    or eligible_verified_native4k_install_retry(
                        item, receipt, new_fp, proof)):
                selected = item
                print("VERIFIED_INSTALL_FAILED_DEEP_RETRY", item["id"],
                      "previous", receipt.get("run_id"), flush=True)
                break
    # Recover EXACTLY ONE pinned Cartoon B episode after the verified live
    # 403 incident. No other reservation, provider, clip or public video
    # becomes eligible. A fresh run writes attempt_count=2 and cannot reenter.
    if selected is None:
        for item in listed:
            if item.get("id") != OWNER_CARTOON_B_403_RESUME["id"]:
                continue
            _, receipt = records[item["id"]]
            if (receipt is None or receipt.get("state") != "reserved"
                    or receipt.get("run_id") != OWNER_CARTOON_B_403_RESUME["old_run"]
                    or not unpublished(item["id"])):
                continue
            current_fingerprint = preview_fingerprint(item)
            if eligible_verified_cartoon_b_403_resume(
                    item, receipt, current_fingerprint,
                    failed_action_conclusion(receipt.get("run_id")),
                    production_cartoon_b_http_ready()):
                selected = item
                print("VERIFIED_LIVE_CARTOON_B_403_PRIVATE_RESUME",
                      item["id"], "old_run", receipt["run_id"], flush=True)
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
        detail=("source_blocker=NATIVE_2K_SOURCE_METADATA_UNVERIFIED\n"
                if native_blocked else "")
        output.write_text("has_job=false\n"+detail,encoding="utf8")
        if native_blocked:
            print("FACTORY_WAITING_FOR_NATIVE_2K_SOURCE_PROVENANCE",
                  native_blocked,"no false 448x800 upscale",flush=True)
        else:
            print("QUEUE_EMPTY: no new or revised legally cleared video to render")
        return
    item = selected
    slug = item["id"]
    existing, old_receipt = records[slug]
    # GitHub could consume successive original episodes while the media
    # origin is offline, despite producing no usable MP4. No permanent source/episode reservation
    # until this EXACT episode has reachable owner media and approved TTS.
    # Provider availability is not a substitute for source hash, QA or review.
    if os.environ.get("GUSTAVA_PROVIDER_PREFLIGHT") == "1":
        from provider_preflight import require_available
        try:
            require_available(item)
        except RuntimeError as exc:
            message = str(exc)
            if not message.startswith("PROVIDER_PREFLIGHT_"):
                raise
            output.write_text(
                "has_job=false\nprovider_blocker=" + message[:240] + "\n",
                encoding="utf8")
            print("FACTORY_PROVIDER_OFFLINE_NO_RESERVATION", slug, message, flush=True)
            return
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
        "selfhosted_voice_id": item.get("selfhosted_voice_id"),
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
    contents["selfhosted_reference_sha256"] = report.get("selfhosted_reference_sha256")
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
    # GitHub's shared render-ledger branch is also written by rolling-batch,
    # Buffer and future render workers. Even a content PUT with the correct
    # file SHA can receive HTTP 409 when another file committed to the same
    # branch between the file read and write. This must not strand an
    # otherwise valid, finished and independently QA-passed MP4 forever.
    # On conflict re-read the EXACT same reservation and retry only if its
    # run ID, source/fingerprint and ALL fields remain unchanged.
    original = json.loads(base64.b64decode(item["content"]))
    from time import sleep
    last_conflict = None
    for attempt in range(4):
        current = item if attempt == 0 else api(path)
        if (not current or not current.get("sha")
                or json.loads(base64.b64decode(current["content"])) != original):
            raise RuntimeError(
                "Render receipt changed during HTTP 409 recovery; "
                "no blind publication, retry or overwrite"
            )
        try:
            store(path, contents, "Rendered unique Shorts preview " + slug, current["sha"])
        except RuntimeError as exc:
            if "GitHub queue operation failed HTTP 409" not in str(exc):
                raise
            last_conflict = exc
            if attempt >= 3:
                break
            sleep(0.5 * (2 ** attempt))
            continue
        print("QUEUE_PREVIEW_READY", slug)
        return
    raise RuntimeError(
        "GitHub queue finish contention after bounded 409 retries; "
        "MP4 retained privately and NOT published"
    ) from last_conflict


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
