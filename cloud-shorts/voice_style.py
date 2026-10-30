#!/usr/bin/env python3
"""Natural, low male narration profile for GUSTAVA motorcycle Shorts.

The source remains the consented Russian Kokoro male actor Dima. We lower
pitch by approximately 4.3 semitones and let formants shift with it (more chest resonance),
without introducing another voice layer or altering reading speed. A subtle low-mid lift and soft saturation add a restrained gravelly edge;
no synthetic growls, hard clipping or fake 'stereo' vocals.

The result is 24 kHz, mono PCM for the existing centered stereo music mix.
The acoustics of a male voice cannot be certified by DSP metadata alone:
blind ear-test approval is still recommended.
"""
from __future__ import annotations

import argparse
from array import array
import hashlib
import json
from math import log10, sqrt
from pathlib import Path
import subprocess
import tempfile
import wave

PROFILE_ID = "gustava_male_deep_v3"
SPEAKER = "dima"
MODEL = "zaakirio/kokoro-ru"
PITCH = 0.78
SAMPLE_RATE = 24000
MIN_SECONDS = 3.0
MAX_SECONDS = 35.0

FILTER = (
    "rubberband=pitch=0.78:formant=shifted:transients=crisp:"
    "window=standard:pitchq=quality,"
    "highpass=f=63,"
    "equalizer=f=165:t=q:w=1.1:g=3.3,"
    "equalizer=f=3000:t=q:w=1.2:g=1.5,"
    "acompressor=threshold=0.17:ratio=2.0:attack=12:release=110:makeup=1.10,"
    "asoftclip=type=tanh:threshold=0.88,"
    "alimiter=limit=0.93"
)


def verify_pcm(wav):
    """Protect one full mono narration from silence, truncation and clipping."""
    with wave.open(str(wav), "rb") as f:
        channels = f.getnchannels()
        width = f.getsampwidth()
        rate = f.getframerate()
        n = f.getnframes()
        if channels != 1 or width != 2 or rate != SAMPLE_RATE:
            raise ValueError("Narration must be 24kHz 16bit centered mono PCM")
        duration = n / float(rate)
        if not MIN_SECONDS <= duration <= MAX_SECONDS:
            raise ValueError("Narration duration outside 3-35 seconds")
        pcm = array("h")
        pcm.frombytes(f.readframes(n))
    if not pcm:
        raise ValueError("Narration PCM empty")
    peak = max(abs(x) for x in pcm) / 32768.
    rms = sqrt(sum((x / 32768.) ** 2 for x in pcm) / len(pcm))
    clipping = sum(abs(x) >= 32700 for x in pcm) / len(pcm)
    if peak < .012 or rms < .007:
        raise ValueError("Deep male narration has too little sound")
    if peak > .995 or clipping > .001:
        raise ValueError("Deep male narration is digitally clipped")
    return {"duration_seconds": round(duration, 3), "peak_dbfs": round(20 * log10(peak), 2),
            "rms_dbfs": round(20 * log10(rms), 2), "clipped_fraction": round(clipping, 6)}


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as data:
        for part in iter(lambda: data.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def profile_report_path(wav):
    return Path(wav).with_suffix(".profile.json")


def validate_report(wav):
    """Require cryptographic binding of profile to the ACTUAL final voice WAV."""
    path = profile_report_path(wav)
    if not path.is_file():
        raise ValueError("Deep male voice-profile proof missing")
    obj = json.loads(path.read_text(encoding="utf8"))
    if obj.get("profile_id") != PROFILE_ID or obj.get("speaker") != SPEAKER:
        raise ValueError("Unapproved voice/speaker")
    if obj.get("pitch") != PITCH or obj.get("processed_wav_sha256") != sha256(wav):
        raise ValueError("Voice processing checksum or settings mismatch")
    stats = verify_pcm(wav)
    if abs(float(obj.get("audio", {}).get("duration_seconds", 0)) -
           stats["duration_seconds"]) > .01:
        raise ValueError("Voice profile duration mismatch")
    if obj.get("quality_passed") is not True:
        raise ValueError("Voice timbre profile quality check is not passed")
    return obj


def apply(wav, ffmpeg="ffmpeg"):
    """Replace a newly generated mono voice WAV atomically; fail closed."""
    wav = Path(wav)
    before = verify_pcm(wav)
    temp = wav.with_name(wav.stem + ".deep-male.tmp.wav")
    report = profile_report_path(wav)
    report.unlink(missing_ok=True)
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
             "-i", str(wav), "-vn", "-af", FILTER,
             "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le",
             str(temp)],
            capture_output=True, text=True, timeout=100,
        )
        if result.returncode != 0 or not temp.is_file():
            raise RuntimeError("FFmpeg rubberband unavailable or voice processing failed: "
                               + result.stderr[-480:])
        after = verify_pcm(temp)
        if abs(after["duration_seconds"] - before["duration_seconds"]) > .30:
            raise RuntimeError("Deep voice processing changed speech timing")
        temp.replace(wav)
        proof = {
            "profile_id": PROFILE_ID, "speaker": SPEAKER,
            "source_model": MODEL, "pitch": PITCH,
            "formants": "shifted", "synthesized_voice_only": True,
            "timbre_processing": "warm_chest_soft_saturation_v3",
            "quality_passed": True, "processed_wav_sha256": sha256(wav),
            "audio": after,
            "disclaimer": "Pitch/tone DSP is not a human assessment of perceived timbre.",
        }
        report.write_text(json.dumps(proof, ensure_ascii=False, indent=2)+"\n", encoding="utf8")
        validate_report(wav)
        print("GUSTAVA_DEEP_MALE_NARRATOR_READY", PROFILE_ID,
              "pitch", PITCH, "rms_dbfs", after["rms_dbfs"], flush=True)
        return after["duration_seconds"]
    finally:
        temp.unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--wav", type=Path, required=True)
    p.add_argument("--check-only", action="store_true")
    args = p.parse_args()
    if args.check_only:
        print("GUSTAVA_MALE_PROFILE_VERIFIED", validate_report(args.wav)["profile_id"])
    else:
        apply(args.wav)


if __name__ == "__main__":
    main()
