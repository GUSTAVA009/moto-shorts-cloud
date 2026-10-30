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
    "track_a": (
        "На гоночной трассе всё происходит очень быстро. Перед поворотом "
        "райдер выбирает линию движения. Важно смотреть на дорогу и держать "
        "ровный темп. Каждый участок трассы требует внимания. "
        "А тебе нравятся такие гонки?"
    ),
    "track_b": (
        "Перед нами трасса для мотокросса. Здесь повороты, песок и кочки. "
        "Райдер смотрит вперёд и выбирает линию движения. "
        "Скорость без контроля не поможет. Главное — внимание "
        "и хорошая подготовка. Любишь смотреть такие гонки?"
    ),
    "track_c": (
        "Впереди поворот на гоночной трассе. Райдер внимательно смотрит "
        "на дорогу и выбирает удобную линию движения. "
        "Здесь важны подготовка, точные движения и контроль. "
        "А какой момент гонки нравится тебе больше?"
    ),
    "track_d": (
        "На трассе для гонок много поворотов. После старта каждый райдер "
        "ищет удобную линию. Здесь важны контроль, внимание и спокойные "
        "действия. Даже на высокой скорости нужно смотреть вперёд. "
        "А ты любишь мотокросс?"
    ),
    "repair_a": (
        "В мастерской всегда найдётся важная работа. Перед поездкой нужно "
        "осмотреть колёса, проверить тормоза и оценить состояние цепи. "
        "На дороге каждая деталь имеет значение. "
        "А ты часто проверяешь технику?"
    ),
    "repair_b": (
        "В мастерской всегда найдётся важная работа. Перед поездкой нужно "
        "осмотреть колёса, проверить тормоза и оценить состояние цепи. "
        "На дороге каждая деталь имеет значение. "
        "А ты тоже так делаешь?"
    ),
    "repair_c": (
        "В мастерской всегда найдётся важная работа. Перед поездкой нужно "
        "осмотреть колёса, проверить тормоза и оценить состояние цепи. "
        "На дороге каждая деталь имеет значение. "
        "А ты часто проверяешь колёса?"
    ),
    "repair_d": (
        "В мастерской важна каждая деталь. Перед поездкой стоит осмотреть "
        "колёса, проверить тормоза и состояние цепи. "
        "Небольшая проверка помогает заметить проблему заранее. "
        "А что ты проверяешь первым делом?"
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
    best_by_topic = {
        topic: best_candidate([r for r in rows if r["id"].startswith(topic+"_")])
        for topic in ("track","repair")
    }
    summary={"version":2,"voice_profile":"gustava_native_bass_baritone_v6",
             "tests":rows,"best_by_topic":best_by_topic,
             "all_automatic_quality_gates_still_required":True}
    (work/"results.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    for topic, best in best_by_topic.items():
        if best:
            print("V6_RUSSIAN_SCRIPT_FULL_ASR_PASSED",topic,best["id"],
                  best["lexical_coverage"],flush=True)
        else:
            print("V6_RUSSIAN_SCRIPT_NO_FULL_ASR_PASS",topic,flush=True)
    # Requires a passing source-audio transcript for both independent episodes.
    return 0 if all(best_by_topic.values()) else 1


if __name__=="__main__":
    raise SystemExit(main())
