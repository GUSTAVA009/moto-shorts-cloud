#!/usr/bin/env python3
"""One-time, tightly checked catalog edit for a verified private Qwen MP4.

The 294-KB source catalog is patched in a GitHub runner, rather than
smuggling a giant replacement payload through a connector. This helper
cannot authorize uploads, change the reference voice, or replace footage.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "episodes.json"
EPISODE = "moto-roadtrip-5b98825cae72"
OLD = ("Мотоцикл в путешествии — скука? Здесь райдер едет по горному маршруту. "
       "На другом видео — гонка на треке. Разные люди и съёмки. Что ближе тебе?")
NEW = ("Горная дорога или трек? На первом видео райдер путешествует среди гор. "
       "На втором — мотоциклист едет по треку. Две разные поездки. Что ближе тебе?")
PRIOR_MP4 = "68ed361b2d2b6936cfe224eb7072b3896b2c005b205f8c349bef487038191b86"
SOURCE_IDS = ["32659157", "31894372"]


def change(catalog):
    if catalog.get("version") != 5:
        raise ValueError("Unexpected catalog version")
    matches = [ep for ep in catalog["episodes"] if ep.get("id") == EPISODE]
    if len(matches) != 1:
        raise ValueError("Exact episode missing or duplicated")
    ep = matches[0]
    if ep.get("mixed_editorial_revision_requested") is True:
        if ep.get("narration") == NEW:
            return False
        raise ValueError("Conflicting existing revision")
    if ep.get("narration") != OLD:
        raise ValueError("Source narration changed: no blind overwrite")
    if (ep.get("auto_publish") is not False
            or ep.get("auto_preview") is not True
            or ep.get("voice_engine") != "gustava_selfhosted_qwen3"
            or ep.get("voice_profile") != "gustava_original_qwen3_v1"
            or [str(x.get("source_page", "")).rstrip("/").split("-")[-1]
                for x in ep["footage"]] != SOURCE_IDS):
        raise ValueError("Immutable unpublished speaker or footage changed")
    if not 125 <= len(NEW) <= 160:
        raise ValueError("Two genuine shots cannot cover longer speech")
    ep["title"] = "Горная дорога или трек? Какой путь твой? #shorts"
    ep["narration"] = NEW
    ep["description"] = (
        "Два независимых лицензированных эпизода: горная поездка и движение "
        "мотоциклиста по треку. Факт соревнования или единого события "
        "в этих кадрах не подтверждён.\n\n#shorts"
    )
    ep["caption_start"] = "ГОРНАЯ ДОРОГА ИЛИ ТРЕК?"
    ep["caption_middle"] = "РАЙДЕР ЕДЕТ ПО ТРЕКУ"
    ep["caption_end"] = "КАКОЙ МАРШРУТ ТВОЙ?"
    ep["clean_speech_intro_seconds"] = 3.3
    ep["mixed_editorial_revision_requested"] = True
    ep["mixed_editorial_revision_reason"] = "actual_final_mix_asr_and_visual_truth_fix"
    ep["mixed_editorial_revision_evidence"] = {
        "prior_run_id": "41333288738",
        "prior_mp4_sha256": PRIOR_MP4,
        "prior_raw_asr_coverage": 1.0,
        "prior_mixed_asr_coverage": 0.957,
        "prior_qa_note": "WAV 1.000; final MP4 'скука' recognised as 'с Кука'",
        "prior_visual_note": "one rider on track; race not established",
        "source_ids": SOURCE_IDS,
        "immutable_licensed_sources": True,
        "same_selfhosted_narrator": True,
        "publication_authorized": False,
        "max_total_attempts": 4,
        "visual_review_required": True,
        "voice_timbre_review_required": True,
    }
    return True


def main():
    data = json.loads(CATALOG.read_text(encoding="utf8"))
    if change(data):
        CATALOG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
        print("PRIVATE_EVIDENCE_REPAIR_APPLIED", EPISODE)
    else:
        print("PRIVATE_EVIDENCE_REPAIR_ALREADY_APPLIED", EPISODE)


if __name__ == "__main__":
    main()
