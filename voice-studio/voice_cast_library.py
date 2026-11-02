"""Real, private HAPYCH Voice Cast audition library (no publication rights grant).

17 role renderings from NINE pre-existing Qwen3-TTS 0.6B CustomVoice speakers.
Never call them 17 trained voice identities.  User-facing GET routes are
strictly behind the owner portal's existing signed session.  Only exact
whitelisted per-role MP3 bytes with SHA-256 provenance may be served.
No changes to the narrator endpoint, its pinned reference or Buffer gates.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re

DEFAULT_ROOT = Path("/opt/hapych-factory-voice/private/auditions_20261102")
MODEL = "Qwen3-TTS-12Hz-0.6B-CustomVoice"
SPEAKERS = frozenset({
    "eric","aiden","dylan","ryan","uncle_fu",
    "serena","vivian","ono_anna","sohee",
})
ROLE_IDS = frozenset({
    "child_cartoon","comic_bass_cartoon","medium_warm","grandpa_biker",
    "son_teen","father","mother","grandma","mechanic","sport_energy",
    "soft_female","comic_villain","young_female","dry_humor",
    "news_story","warm_biker_woman","cartoon_spring_nasal_original_v1",
})
SHA = re.compile(r"[a-f0-9]{64}\Z")
NAME = re.compile(r"\d{2}_[a-z0-9_]+\.mp3\Z")


class CastUnavailable(ValueError):
    """No private audition package, wrong origin or corrupted sample."""


def cast_root(root=None):
    path = Path(root if root is not None else os.environ.get(
        "HAPYCH_CAST_AUDITION_ROOT", str(DEFAULT_ROOT)))
    if not path.is_dir() or path.is_symlink():
        raise CastUnavailable("VOICE_CAST_PRIVATE_AUDITION_PACK_NOT_FOUND")
    return path


def _read_catalog(root=None):
    path = cast_root(root)
    manifest = path / "voice_pack_manifest.json"
    if not manifest.is_file() or manifest.is_symlink() or manifest.stat().st_size > 120000:
        raise CastUnavailable("VOICE_CAST_MANIFEST_UNAVAILABLE")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise CastUnavailable("VOICE_CAST_MANIFEST_INVALID") from None
    if (data.get("model") != MODEL
            or data.get("source_count") != len(SPEAKERS)
            or data.get("role_variants") != len(ROLE_IDS)
            or data.get("production_enabled") is not False):
        raise CastUnavailable("VOICE_CAST_PROVENANCE_NOT_VERIFIED")
    rows = data.get("voices")
    if not isinstance(rows,list) or len(rows)!=len(ROLE_IDS):
        raise CastUnavailable("VOICE_CAST_ROLE_COUNT_MISMATCH")
    roles={}
    for i, row in enumerate(rows,1):
        if not isinstance(row,dict):
            raise CastUnavailable("VOICE_CAST_ROLE_INVALID")
        rid=row.get("id")
        if (rid not in ROLE_IDS or rid in roles
                or row.get("speaker") not in SPEAKERS
                or row.get("production_enabled") is not False
                or type(row.get("asr_passed")) is not bool):
            raise CastUnavailable("VOICE_CAST_ROLE_NOT_AUDITION_ONLY")
        name=row.get("mp3_file")
        if (not isinstance(name,str)
                or name != f"{i:02d}_{rid}.mp3"
                or NAME.fullmatch(name) is None):
            raise CastUnavailable("VOICE_CAST_BAD_MEDIA_PATH")
        file = path / "by_role" / name
        if not file.is_file() or file.is_symlink():
            raise CastUnavailable("VOICE_CAST_AUDIO_MISSING")
        size=file.stat().st_size
        if not 1000 <= size <= 1500000:
            raise CastUnavailable("VOICE_CAST_MEDIA_SIZE_INVALID")
        digest=row.get("sha256_mp3")
        if not isinstance(digest,str) or not SHA.fullmatch(digest):
            raise CastUnavailable("VOICE_CAST_SHA_MISSING")
        if hashlib.sha256(file.read_bytes()).hexdigest()!=digest:
            raise CastUnavailable("VOICE_CAST_SHA_MISMATCH")
        qa=row.get("asr_check")
        if (not isinstance(qa,dict)
                or qa.get("engine")!="faster-whisper-small-cpu-int8"
                or qa.get("audio_sha256")!=row.get("sha256_wav")
                or type(qa.get("coverage")) not in (float,int)
                or type(qa.get("precision")) not in (float,int)
                or not 0<=qa["coverage"]<=1
                or not 0<=qa["precision"]<=1
                or bool(qa["coverage"]>=.97 and qa["precision"]>=.97)
                     != row["asr_passed"]):
            raise CastUnavailable("VOICE_CAST_ASR_EVIDENCE_MISMATCH")
        duration=row.get("seconds")
        shift=row.get("pitch_semitones")
        if (not isinstance(duration,(float,int)) or not 2<=duration<=30
                or not isinstance(shift,(float,int)) or not -3<=shift<=3
                or not isinstance(row.get("name_ru"),str)
                or len(row["name_ru"])>90):
            raise CastUnavailable("VOICE_CAST_AUDIO_METADATA_INVALID")
        roles[rid]=(row,file)
    if set(roles)!=ROLE_IDS:
        raise CastUnavailable("VOICE_CAST_ROLE_SET_MISMATCH")
    return roles


def available_auditions(root=None):
    roles=_read_catalog(root)
    return {
        "count":len(roles),
        "independent_stock_speakers":len(SPEAKERS),
        "production_approved":0,
        "short_russian_canary_passed":sum(1 for x,_ in roles.values() if x["asr_passed"]),
        "short_russian_canary_failed":sum(1 for x,_ in roles.values() if not x["asr_passed"]),
        "status":"private_auditions_only_awaiting_owner_and_russian_asr",
        "voices":[{
            "id":key, "name_ru":row["name_ru"], "speaker":row["speaker"],
            "pitch_semitones":row["pitch_semitones"],
            "duration_seconds":row["seconds"], "generated":True,
            "short_russian_canary_passed":row["asr_passed"],
            "short_russian_coverage":row["asr_check"]["coverage"],
            "full_russian_asr_verified":False, "production_enabled":False,
        } for key,(row,_) in roles.items()],
    }


def audition_audio(role_id,root=None):
    if role_id not in ROLE_IDS:
        raise CastUnavailable("VOICE_CAST_UNKNOWN_ROLE")
    roles=_read_catalog(root)
    # The catalog is revalidated on EACH authenticated read; no stale file
    # cache bypasses an on-disk replacement or SHA mismatch.
    return roles[role_id][1].read_bytes()
