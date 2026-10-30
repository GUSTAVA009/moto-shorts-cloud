#!/usr/bin/env python3
"""Fail-closed Russian narration QA using local speech recognition.

The recognizer is an independent check, not proof of perfect pronunciation.
Missing words or a clipped ending must keep the video out of auto-publication.
No speech recognition or paid service runs during offline unit tests.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from difflib import SequenceMatcher
from pathlib import Path
import re
import sys
import wave

from voice_style import PROFILE_ID as MALE_PROFILE, validate_report as validate_male_style
from native_bass_voice import (PROFILE_ID as NATIVE_BASS_PROFILE,
    VOICE_ENGINE as NATIVE_BASS_ENGINE,
    validate_report as validate_native_bass_report)
from deep_voice import (VOICE_ENGINE as DEEP_ENGINE,
                        PROFILE_ID as DEEP_PROFILE,
                        verify_profile as verify_deep_profile)


# ASR commonly writes "тысяча девятьсот восемьдесят второго" as "1982".
# Normalize numerals on BOTH sides instead of falsely claiming four words vanished.
_NUMBERS = {
    "ноль": 0, "один": 1, "одна": 1, "одно": 1, "две": 2, "два": 2,
    "второго": 2, "второй": 2, "вторая": 2, "вторую": 2,
    "три": 3, "третий": 3, "четыре": 4, "пять": 5, "шесть": 6,
    "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
    "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13,
    "четырнадцать": 14, "пятнадцать": 15, "шестнадцать": 16,
    "семнадцать": 17, "восемнадцать": 18, "девятнадцать": 19,
    "двадцать": 20, "тридцать": 30, "сорок": 40,
    "пятьдесят": 50, "шестьдесят": 60, "семьдесят": 70,
    "восемьдесят": 80, "девяносто": 90, "сто": 100,
    "двести": 200, "триста": 300, "четыреста": 400,
    "пятьсот": 500, "шестьсот": 600, "семьсот": 700,
    "восемьсот": 800, "девятьсот": 900,
    "тысяча": 1000, "тысячи": 1000, "тысяч": 1000,
}


# Single verified Russian/Latin loanword spelling equivalence observed in
# exact MP4 ASR: audio said «мотокросс», Whisper printed "motocross".
# DO NOT transliterate arbitrary Latin text: that would mask real omissions.
_ASR_SPELLING_EQUIVALENTS = {"motocross": "мотокросс"}


def tokens(text):
    normalized = str(text).casefold().replace("ё", "е")
    # "восьмидесятых" and the ASR transcription "80-х" mean the same decade,
    # not a fabricated or mispronounced number.
    normalized = re.sub(r"\bвосьмидесятых\b", "80", normalized)
    normalized = re.sub(r"\b80[-–][хx]\b", "80", normalized)
    raw = [_ASR_SPELLING_EQUIVALENTS.get(t, t)
           for t in re.findall(r"[а-яa-z0-9]+", normalized)]
    out = []
    i = 0
    while i < len(raw):
        if raw[i] not in _NUMBERS:
            out.append(raw[i])
            i += 1
            continue
        value, n = 0, i
        while n < len(raw) and raw[n] in _NUMBERS:
            unit = _NUMBERS[raw[n]]
            if unit == 1000 and value and value < 10:
                value *= 1000
            else:
                value += unit
            n += 1
        out.append(str(value))
        i = n
    return out


def match_ratio(reference, actual):
    if not reference:
        return 0.0
    matches = SequenceMatcher(None, reference, actual, autojunk=False).get_matching_blocks()
    return sum(block.size for block in matches) / len(reference)


def score(reference, recognized):
    expected, heard = tokens(reference), tokens(recognized)
    coverage = match_ratio(expected, heard)
    n = min(5, len(expected))
    first = match_ratio(expected[:n], heard[:max(n + 3, 8)])
    last = match_ratio(expected[-n:], heard[-max(n + 3, 8):])
    # Missing sentence tails and short first words are treated as serious faults.
    end_exact = bool(expected and heard and expected[-1] in heard[-3:])
    tail_three = match_ratio(expected[-3:], heard[-5:])
    numerics_match = ([x for x in expected if x.isdigit()] ==
                      [x for x in heard if x.isdigit()])
    passed = bool(len(expected) >= 6 and coverage >= 0.97
                  and first >= 0.95 and last >= 0.95
                  and end_exact and tail_three >= 0.99 and numerics_match)
    return {
        "passed": passed,
        "status": "passed" if passed else "manual_review_required",
        "lexical_coverage": round(coverage, 3),
        "beginning_coverage": round(first, 3),
        "ending_coverage": round(last, 3),
        "final_three_coverage": round(tail_three, 3),
        "final_word_present": end_exact,
        "numerics_match": numerics_match,
        "expected_words": len(expected),
        "recognized_words": len(heard),
        "recognized_text": str(recognized).strip()[:1200],
        "note": "ASR comparison is a quality gate, not a certificate of pronunciation."
    }


def read_duration(path):
    with wave.open(str(path), "rb") as f:
        if f.getnchannels() != 1:
            raise ValueError("Narration must be mono")
        duration = f.getnframes() / f.getframerate()
        if not 3.0 <= duration <= 35.0:
            raise ValueError("Narration WAV duration outside permitted Shorts window")
        return duration


def check(episode, wav, model="small"):
    from asr_fallback import transcribe
    audio_path = Path(wav)
    duration = read_duration(audio_path)
    recognized, asr_engine = transcribe(audio_path, model)
    result = score(episode["narration"], recognized)
    result.update({
        "episode_id": episode["id"],
        "duration_seconds": round(duration, 3),
        "wav_sha256": hashlib.sha256(audio_path.read_bytes()).hexdigest(),
        "engine": asr_engine,
        "model": model,
    })
    if episode.get("voice_engine") == DEEP_ENGINE:
        try:
            report = verify_deep_profile(audio_path, episode)
            result["male_voice_verified"] = True
            result["voice_profile"] = DEEP_PROFILE
            result["voice_speaker"] = "deep"
            result["voice_provider"] = "aidocmaker.com"
            result["voice_source_license"] = "AI Doc Maker attribution"
            result["voice_source_audio_sha256"] = report["source_audio_sha256"]
        except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
            result["male_voice_verified"] = False
            result["voice_profile"] = None
            result["passed"] = False
            result["status"] = "manual_review_required"
            result["reason"] = "REAL_DEEP_VOICE_SOURCE_NOT_VERIFIED: " + type(exc).__name__
    elif episode.get("voice_engine") == NATIVE_BASS_ENGINE:
        try:
            profile=validate_native_bass_report(audio_path)
            result["male_voice_verified"]=True
            result["voice_profile"]=NATIVE_BASS_PROFILE
            result["voice_profile_pitch"]=1.0
            result["voice_speaker"]=profile["speaker"]
            result["voice_source_license"]=profile["license"]
        except (ValueError,OSError,TypeError,KeyError,json.JSONDecodeError) as exc:
            result["male_voice_verified"]=False
            result["voice_profile"]=None
            result["passed"]=False
            result["status"]="manual_review_required"
            result["reason"]="NATIVE_BASS_PROFILE_MISSING_OR_INVALID: "+type(exc).__name__
    elif episode.get("voice_engine") == "kokoro_ru_dima":
        # Source WAV SHA must match the exact approved low-male narrator.
        # A previous bright-voiced Dima preview is NOT eligible for Buffer.
        try:
            profile = validate_male_style(audio_path)
            result["male_voice_verified"] = True
            result["voice_profile"] = MALE_PROFILE
            result["voice_profile_pitch"] = profile["pitch"]
        except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
            result["male_voice_verified"] = False
            result["voice_profile"] = None
            result["passed"] = False
            result["status"] = "manual_review_required"
            result["reason"] = "DEEP_MALE_PROFILE_MISSING_OR_INVALID: " + type(exc).__name__
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", type=Path, default=Path(__file__).with_name("episodes.json"))
    p.add_argument("--episode", required=True)
    p.add_argument("--wav", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--model", default="small")
    args = p.parse_args()
    episodes = json.loads(args.catalog.read_text(encoding="utf8"))["episodes"]
    chosen = next((e for e in episodes if e["id"] == args.episode), None)
    if chosen is None:
        raise SystemExit("Episode not found; no audio QA")
    try:
        report = check(chosen, args.wav, args.model)
    except Exception as exc:
        report = {"episode_id": args.episode, "status": "manual_review_required",
                  "passed": False, "reason": "ASR_QA_UNAVAILABLE: " + type(exc).__name__,
                  "debug_exception": str(exc)[:260]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print("VOICE_QA", report["status"], "coverage", report.get("lexical_coverage", "unknown"),
          "reason", report.get("reason","none"),flush=True)
    # The render is retained for a human reviewer even if automatic release is blocked.
    return 0


if __name__ == "__main__":
    sys.exit(main())
