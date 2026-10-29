#!/usr/bin/env python3
"""Bounded unattended repairs of Russian narration and soundtrack masking.

Never edits lyrics or teaches a recognizer an incorrect transcript. Recreates
the same licensed original with a conservatively different speech pace / quieter
original music. Human review remains necessary when all attempts fail.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
# Narrator remains centered in stereo; lowering background only can never
# fix a missing spoken consonant but does improve final mixed intelligibility.
PROFILES = ((1.00, .34), (.95, .22), (1.05, .14))
MIN_COVERAGE = .97


def passes(voice, mixed, episode_id):
    return bool(
        voice.get("episode_id") == episode_id
        and mixed.get("episode_id") == episode_id
        and all(report.get("passed") is True and report.get("status") == "passed"
                and report.get("lexical_coverage", 0) >= MIN_COVERAGE
                and report.get("final_word_present") is True
                and report.get("numerics_match", True) is True
                for report in (voice, mixed))
        and mixed.get("source") == "FINAL_MIXED_MP4"
        and mixed.get("numerics_match") is True
    )


def load_report(path):
    if not path.is_file():
        return {"passed": False, "status": "manual_review_required",
                "reason": "MISSING_QA_REPORT"}
    try:
        return json.loads(path.read_text(encoding="utf8"))
    except (OSError, ValueError):
        return {"passed": False, "status": "manual_review_required",
                "reason": "CORRUPT_QA_REPORT"}


def run_command(args, env=None):
    result = subprocess.run(args, env=env, check=False, timeout=1200)
    if result.returncode != 0:
        raise RuntimeError("QA repair subprocess exited " + str(result.returncode))


def evaluate(episode_id, work, dist, speed, gain):
    env = dict(os.environ, GUSTAVA_TTS_SPEED=str(speed),
               GUSTAVA_MUSIC_GAIN=str(gain))
    run_command([sys.executable, str(HERE / "render_episode.py"),
                 "--episode", episode_id], env)
    voice = dist / "voice_qa.json"
    mixed = dist / "mixed_audio_qa.json"
    run_command([sys.executable, str(HERE / "voice_qa.py"),
                 "--episode", episode_id, "--wav", str(work / "new_narration.wav"),
                 "--out", str(voice)])
    run_command([sys.executable, str(HERE / "mixed_audio_qa.py"),
                 "--episode", episode_id,
                 "--mp4", str(dist / (episode_id + ".mp4")),
                 "--out", str(mixed)])
    return load_report(voice), load_report(mixed)


def repair(episode_id, profiles=PROFILES, runner=evaluate):
    if not (episode_id and episode_id.replace("-", "").isalnum()):
        raise ValueError("Invalid episode identity")
    work = HERE / "work" / episode_id
    dist = HERE / "dist" / "new" / episode_id
    dist.mkdir(parents=True, exist_ok=True)
    audit = []
    for attempt, (speed, gain) in enumerate(profiles, start=1):
        try:
            voice, mixed = runner(episode_id, work, dist, speed, gain)
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
            audit.append({"attempt": attempt, "status": "technical_error",
                          "reason": type(exc).__name__, "speech_speed": speed,
                          "music_gain": gain})
            # A broken/downloaded source requires different rights-cleared
            # footage; repeating the same network request blindly is unsafe.
            print("QA_REPAIR_TECHNICAL_ERROR", attempt, type(exc).__name__, flush=True)
            break
        ok = passes(voice, mixed, episode_id)
        audit.append({
            "attempt": attempt, "status": "passed" if ok else "failed_speech_qa",
            "speech_speed": speed, "music_gain": gain,
            "raw_coverage": voice.get("lexical_coverage"),
            "mixed_coverage": mixed.get("lexical_coverage"),
            "voice_engine": voice.get("engine"),
            "mixed_engine": mixed.get("engine"),
        })
        print("AUTOREPAIR_ATTEMPT", episode_id, attempt, audit[-1], flush=True)
        if ok:
            break
    else:
        print("AUTOREPAIR_LIMIT_REACHED", episode_id, flush=True)
    result = {"episode_id": episode_id, "quality_passed":
              bool(audit and audit[-1]["status"] == "passed"),
              "attempts": audit}
    (dist / "repair_history.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    if any(x["status"] == "technical_error" for x in audit):
        return 1
    # A valid MP4 with an ASR failure stays as a private artifact; an
    # independent workflow must still reject it before Buffer.
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--episode", required=True)
    args = p.parse_args()
    return repair(args.episode)


if __name__ == "__main__":
    sys.exit(main())
