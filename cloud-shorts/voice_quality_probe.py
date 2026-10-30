#!/usr/bin/env python3
"""Test real native bass-baritone phrase intelligibility before MP4 production.

This workflow does NOT publish, change episode catalog or weaken the ASR gate.
Choose the best full-coverage, fully transcribed Russian phrase without
invented real-life incidents or unlicensed material.
"""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys

from native_bass_voice import render as make_voice, validate_report
from asr_fallback import transcribe
from voice_qa import score

ROOT = Path(__file__).resolve().parent
PHRASES = {
    "f_path": (
        "Вот путь через лес. Перед поездкой важно проверить мотоцикл. "
        "Во время движения нужно видеть повороты и следить за покрытием. "
        "Даже красивый маршрут требует внимания. "
        "А какой маршрут нравится тебе?"
    ),
    "g_clear_road": (
        "Впереди лесная дорога и новый поворот. В дороге лучше смотреть "
        "вперёд и не спешить. Красивый маршрут требует внимания к деталям. "
        "Важно видеть покрытие и держать безопасную дистанцию. "
        "Тебе нравятся такие поездки?"
    ),
    "h_simple": (
        "Впереди лесная дорога и новый поворот. "
        "Смотри на дорогу, не спеши и держи дистанцию. "
        "Красивый маршрут требует внимания к деталям. "
        "Важно видеть покрытие и заранее оценивать повороты. "
        "Тебе нравятся такие поездки?"
    ),
    "i_views": (
        "Перед нами дорога среди деревьев. "
        "Впереди новый поворот, но спешить не стоит. "
        "Красивый маршрут требует внимания к деталям. "
        "Важно видеть покрытие и держать безопасную дистанцию. "
        "А ты любишь такие поездки?"
    ),
}


def best_candidate(rows):
    good=[r for r in rows if r.get("passed") is True]
    if not good:
        return None
    return sorted(good,key=lambda r:(
        r["lexical_coverage"],r["beginning_coverage"],
        r["ending_coverage"], -r["duration_seconds"]),reverse=True)[0]


def main():
    work=ROOT/"dist"/"voice_probes_v6"
    work.mkdir(parents=True,exist_ok=True)
    rows=[]
    for name,phrase in PHRASES.items():
        wav=work/(name+".wav")
        report={"id":name,"text":phrase}
        try:
            duration=make_voice(phrase,wav,speed=1.0)
            validate_report(wav)
            recognized,engine=transcribe(wav,model="small")
            stats=score(phrase,recognized)
            report.update(stats)
            report.update({"engine":engine,"duration_seconds":round(duration,3)})
            subprocess.run(["ffmpeg","-hide_banner","-nostdin","-loglevel","error","-y",
                            "-i",str(wav),"-c:a","libmp3lame","-q:a","3",
                            str(work/(name+".mp3"))],check=True,timeout=50)
            print("V6_VOICE_PROBE",name,"passed",stats["passed"],
                  "coverage",stats["lexical_coverage"],
                  "recognized",repr(recognized[:250]),flush=True)
        except Exception as exc:
            report.update({"passed":False,"reason":type(exc).__name__+": "+str(exc)[:180]})
            print("V6_VOICE_PROBE_FAILED",name,report["reason"],flush=True)
        rows.append(report)
    best=best_candidate(rows)
    summary={"version":1,"voice_profile":"gustava_native_bass_baritone_v6",
             "tests":rows,"best":best,"all_automatic_quality_gates_still_required":True}
    (work/"results.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    if best:
        print("V6_RUSSIAN_SCRIPT_FULL_ASR_PASSED",best["id"],
              best["lexical_coverage"],flush=True)
        return 0
    print("V6_RUSSIAN_SCRIPT_NO_FULL_ASR_PASS: continue text/voice diagnostics; no auto-release",flush=True)
    return 1


if __name__=="__main__":
    raise SystemExit(main())
