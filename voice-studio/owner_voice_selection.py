"""Owner-picked character voices and ORIGINAL cartoon candidate previews.

The user explicitly selected three exact audition assets (mother, grandma,
warm biker woman) and rejected all other *legacy* cast auditions. The stage
remains "owner-picked samples", NOT "public release approved". Both original
GUSTAVA DEEP and private factory voice authentication remain untouched.

No imports of uploaded third-party content, no voice identity impersonation.
All paths live in an owner-private directory. SHA256 is pinned from exact
verified on-server assets matching user-provided files.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re

ROOT = Path("/opt/hapych-factory-voice/private/owner_selected_20261102")
SAMPLE_PROOFS = {
    "warm_biker_woman": {
        "filename": "16_warm_biker_woman.mp3",
        "sha256": "301ace3e5297fe77c868f2071927b2c60ec85f8f1050838194093c548e44a902",
        "label": "Байкерша",
        "source_speaker": "vivian", "pitch_semitones": -0.7,
        "mime_type": "audio/mpeg",
    },
    "mother": {
        "filename": "07_mother.mp3",
        "sha256": "cc8d8a2c494e95514ba8efef8401d419a6466255ec0be701c05e5ec0aa855fc8",
        "label": "Мама",
        "source_speaker": "vivian", "pitch_semitones": 0.0,
        "mime_type": "audio/mpeg",
    },
    "grandma": {
        "filename": "08_grandma_original.wav",
        "sha256": "dc4581ad64d3372cf9a650aa30410b11dfa74729cb74736b57c4ba9cb13e7e89",
        "label": "Бабушка",
        "source_speaker": "ono_anna", "pitch_semitones": -1.5,
        "mime_type": "audio/wav",
    },
}
SAFE_NAME = re.compile(r"(?:CARTOON_[A-Z0-9_]+\.mp3)\Z")
SAFE_ID = re.compile(r"cartoon_[a-z0-9_]{5,50}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")


class SelectionUnavailable(ValueError):
    pass


def _load_json(path, max_bytes=20000):
    if not path.is_file() or path.is_symlink() or path.stat().st_size>max_bytes:
        raise SelectionUnavailable("VOICE_SELECTION_MANIFEST_MISSING_OR_INVALID")
    try:
        data=json.loads(path.read_text("utf8"))
    except (OSError, ValueError, UnicodeError):
        raise SelectionUnavailable("VOICE_SELECTION_MANIFEST_INVALID") from None
    if not isinstance(data,dict):
        raise SelectionUnavailable("VOICE_SELECTION_MANIFEST_INVALID")
    return data


def _bytes_verified(folder, filename, expected):
    if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
        raise SelectionUnavailable("VOICE_SELECTION_INVALID_FILENAME")
    path=folder/filename
    if not path.is_file() or path.is_symlink() or not 1000<=path.stat().st_size<=2_000_000:
        raise SelectionUnavailable("VOICE_SELECTION_AUDIO_UNAVAILABLE")
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=expected:
        raise SelectionUnavailable("VOICE_SELECTION_SHA_MISMATCH")
    if not (data.startswith(b"ID3") or data[:4]==b"RIFF"):
        raise SelectionUnavailable("VOICE_SELECTION_AUDIO_FORMAT_REJECTED")
    return data


def _selection(root):
    folder=Path(root or os.environ.get("HAPYCH_SELECTED_VOICES_ROOT",str(ROOT)))
    if not folder.is_dir() or folder.is_symlink():
        raise SelectionUnavailable("VOICE_SELECTION_ROOT_MISSING")
    m=_load_json(folder/"selection.json")
    if (m.get("version")!=1 or m.get("owner_primary_deep_unchanged") is not True
            or m.get("production_approved_count")!=0
            or m.get("rejected_other_original_cast_roles") is not True
            or set(m.get("selected_roles",[]))!=set(SAMPLE_PROOFS)):
        raise SelectionUnavailable("VOICE_SELECTION_OWNER_PREFERENCES_INVALID")
    samples=m.get("samples")
    if not isinstance(samples,list) or len(samples)!=3:
        raise SelectionUnavailable("VOICE_SELECTION_INCOMPLETE")
    selected={}
    for row in samples:
        if not isinstance(row,dict) or row.get("role_id") not in SAMPLE_PROOFS:
            raise SelectionUnavailable("VOICE_SELECTION_ROLE_UNEXPECTED")
        role=row["role_id"]
        if role in selected:
            raise SelectionUnavailable("VOICE_SELECTION_ROLE_DUPLICATE")
        proof=SAMPLE_PROOFS[role]
        if (row.get("owner_audition_selected") is not True
                or row.get("production_enabled") is not False
                or row.get("can_use_as_default_gustava_narrator") is not False
                or row.get("reference_sha256")!=proof["sha256"]
                or row.get("source_speaker")!=proof["source_speaker"]
                or row.get("pitch_semitones")!=proof["pitch_semitones"]
                or row.get("reference_file")!=str(folder/proof["filename"])):
            raise SelectionUnavailable("VOICE_SELECTION_REFERENCE_NOT_VERIFIED")
        _bytes_verified(folder,proof["filename"],proof["sha256"])
        selected[role]=(proof,folder)
    return selected,folder


def _cartoon_candidates(folder):
    # Optional separately designed ORIGINALLY SYNTHESIZED cartoon previews.
    # Their presence is never equivalent to owner approval of a character voice.
    manifest=folder/"cartoon_voice_design_manifest.json"
    if not manifest.is_file():
        return {}
    m=_load_json(manifest)
    if (m.get("model")!="Qwen3-TTS-12Hz-1.7B-VoiceDesign"
            or m.get("public_release_approved") is not False
            or m.get("imitates_existing_character") is not False):
        raise SelectionUnavailable("VOICE_DESIGN_PROVENANCE_REJECTED")
    rows=m.get("candidates")
    if not isinstance(rows,list) or not 1<=len(rows)<=3:
        raise SelectionUnavailable("VOICE_DESIGN_COUNT_INVALID")
    result={}
    for row in rows:
        if not isinstance(row,dict):
            raise SelectionUnavailable("VOICE_DESIGN_ROW_INVALID")
        role=row.get("id"); name=row.get("filename"); sha=row.get("sha256")
        if (not isinstance(role,str) or not SAFE_ID.fullmatch(role)
                or role in result or not isinstance(name,str)
                or not SAFE_NAME.fullmatch(name) or not isinstance(sha,str)
                or not HASH.fullmatch(sha) or row.get("production_enabled") is not False
                or row.get("model")!=m["model"]
                or row.get("pitch_semitones")!=-2
                or row.get("asr_short_canary_passed") is not True
                or not isinstance(row.get("duration_seconds"),(int,float))
                or not 2<=row["duration_seconds"]<=35):
            raise SelectionUnavailable("VOICE_DESIGN_CANDIDATE_UNVERIFIED")
        _bytes_verified(folder,name,sha)
        result[role]=(row,folder)
    return result


def owner_voice_list(root=None):
    favorites,folder=_selection(root)
    cartoon=_cartoon_candidates(folder)
    result=[]
    for role in ("warm_biker_woman","mother","grandma"):
        p,_=favorites[role]
        result.append({
            "id":role, "label":p["label"], "owner_selected":True,
            "is_original_cartoon":False, "source_speaker":p["source_speaker"],
            "pitch_semitones":p["pitch_semitones"],
            "mime_type":p["mime_type"], "download_filename":p["filename"],
            "production_enabled":False,
            "audition_short_asr_passed":role!="grandma",
            "note":"Исходная выбранная запись; произношение слова «байкер» требует доработки" if role=="grandma" else "Исходная выбранная запись",
        })
    for role,(row,_) in cartoon.items():
        result.append({
            "id":role, "label":row.get("name_ru","Новый оригинальный мультяшный голос"),
            "owner_selected":False, "is_original_cartoon":True,
            "source_speaker":"VoiceDesign — новая оригинальная акустика",
            "pitch_semitones":-2,
            "mime_type":"audio/mpeg","download_filename":row["filename"],
            "production_enabled":False, "audition_short_asr_passed":True,
            "note":"Новая проба, ожидает твоего прослушивания; не копия персонажа",
        })
    return {
        "selected_count":3,
        "original_cartoon_candidates":len(cartoon),
        "rejected_other_legacy_cast":True,
        "production_approved_count":0,
        "original_deep_unchanged":True,
        "voices":result,
    }


def owner_voice_bytes(role_id,root=None):
    if not isinstance(role_id,str):
        raise SelectionUnavailable("VOICE_SELECTION_UNKNOWN_ROLE")
    selected,folder=_selection(root)
    if role_id in selected:
        proof,_=selected[role_id]
        return _bytes_verified(folder,proof["filename"],proof["sha256"]),proof["mime_type"],proof["filename"]
    cartoon=_cartoon_candidates(folder)
    if role_id not in cartoon:
        raise SelectionUnavailable("VOICE_SELECTION_UNKNOWN_ROLE")
    item,_=cartoon[role_id]
    return _bytes_verified(folder,item["filename"],item["sha256"]),"audio/mpeg",item["filename"]
