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


def tokens(text):
    return re.findall(r"[а-яa-z0-9]+", str(text).casefold().replace("ё", "е"))


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
    passed = bool(len(expected) >= 6 and coverage >= 0.79
                  and first >= 0.60 and last >= 0.60
                  and end_exact and tail_three >= 0.67)
    return {
        "passed": passed,
        "status": "passed" if passed else "manual_review_required",
        "lexical_coverage": round(coverage, 3),
        "beginning_coverage": round(first, 3),
        "ending_coverage": round(last, 3),
        "final_three_coverage": round(tail_three, 3),
        "final_word_present": end_exact,
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


def check(episode, wav, model="base"):
    from faster_whisper import WhisperModel
    audio_path = Path(wav)
    duration = read_duration(audio_path)
    detector = WhisperModel(model, device="cpu", compute_type="int8")
    segments, _ = detector.transcribe(
        str(audio_path), language="ru", beam_size=5, vad_filter=False,
        condition_on_previous_text=False)
    recognized = " ".join(segment.text.strip() for segment in segments)
    result = score(episode["narration"], recognized)
    result.update({
        "episode_id": episode["id"],
        "duration_seconds": round(duration, 3),
        "wav_sha256": hashlib.sha256(audio_path.read_bytes()).hexdigest(),
        "engine": "faster-whisper CPU, independent Russian ASR",
        "model": model,
    })
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", type=Path, default=Path(__file__).with_name("episodes.json"))
    p.add_argument("--episode", required=True)
    p.add_argument("--wav", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--model", default="base")
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
    print("VOICE_QA", report["status"], "coverage", report.get("lexical_coverage", "unknown"))
    # The render is retained for a human reviewer even if automatic release is blocked.
    return 0


if __name__ == "__main__":
    sys.exit(main())
