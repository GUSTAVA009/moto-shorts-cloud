#!/usr/bin/env python3
"""Independently transcribe the FINAL published MP4 audio (voice + music).

A clear raw WAV does not prove the audience can understand the narration
after mixing. This quality gate runs Whisper on the exact finalized MP4 and
fails closed if the file is missing, damaged or the original words are lost.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from voice_qa import score


def media_audio_present(video):
    p = Path(video)
    if p.suffix.lower() != ".mp4" or not p.is_file() or p.stat().st_size < 150_000:
        raise ValueError("Final MP4 missing or unexpectedly small")
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height", "-of", "json", str(p)],
        capture_output=True, text=True, timeout=25, check=True)
    obj = json.loads(result.stdout)
    kinds = {stream.get("codec_type") for stream in obj.get("streams", [])}
    duration = float(obj["format"]["duration"])
    if "audio" not in kinds or "video" not in kinds or not 7 <= duration <= 37:
        raise RuntimeError("Final MP4 lacks valid video, audio, or timing")
    return duration


def check(episode, video, model="base"):
    from asr_fallback import transcribe
    duration = media_audio_present(video)
    recognized, asr_engine = transcribe(video,model)
    result = score(episode["narration"], recognized)
    result.update({
        "episode_id": episode["id"],
        "source": "FINAL_MIXED_MP4",
        "engine": asr_engine+" on FINAL MIXED MP4",
        "duration_seconds": round(duration, 3),
        "mp4_sha256": hashlib.sha256(Path(video).read_bytes()).hexdigest(),
        "model": model,
    })
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode", required=True)
    parser.add_argument("--catalog", type=Path, default=Path(__file__).with_name("episodes.json"))
    parser.add_argument("--mp4", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    entries = json.loads(args.catalog.read_text(encoding="utf8"))["episodes"]
    episode = next((e for e in entries if e["id"] == args.episode), None)
    if episode is None:
        raise SystemExit("EPISODE_MISSING: no final mixed audio QA")
    try:
        report = check(episode, args.mp4)
    except Exception as error:
        report = {"episode_id": args.episode, "source": "FINAL_MIXED_MP4",
                  "status": "manual_review_required", "passed": False,
                  "reason": "FINAL_AUDIO_QA_UNAVAILABLE: " + type(error).__name__,
                  "debug_exception": str(error)[:180]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print("FINAL_MIXED_AUDIO_QA", report["status"],
          "coverage", report.get("lexical_coverage", "unknown"),
          "reason", report.get("reason","none"),flush=True)
    return 0   # Failure is recorded, not hidden; release requires passed=True.


if __name__ == "__main__":
    main()
