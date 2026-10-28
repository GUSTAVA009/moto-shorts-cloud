#!/usr/bin/env python3
"""Generate a new Russian voiceover for each episode on the GitHub runner.

Voice: Piper dmitri medium. Model card declares CC0 training dataset.
Never download a model with a NonCommercial dataset for monetized videos.
"""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
import subprocess
import sys
import urllib.request
import wave

BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/dmitri/medium/"
STEM = "ru_RU-dmitri-medium.onnx"
MODEL_SHA256 = "f073356ebc4bd0f80c5af58df2953a5988bd5bdab1eb38635ce960b071fbefcb"
VOICE_CARD = "https://huggingface.co/rhasspy/piper-voices/blob/main/ru/ru_RU/dmitri/medium/MODEL_CARD"


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as inp:
        for chunk in iter(lambda: inp.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_download(url, target, min_bytes):
    target = Path(target)
    if target.is_file() and target.stat().st_size >= min_bytes:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 MotoShorts/1.0"})
        with urllib.request.urlopen(req, timeout=150) as stream, tmp.open("wb") as output:
            while True:
                part = stream.read(1024 * 1024)
                if not part:
                    break
                output.write(part)
                if output.tell() > 180_000_000:
                    raise RuntimeError("Unexpected download size")
        if tmp.stat().st_size < min_bytes:
            raise RuntimeError("Model/config download too small: " + target.name)
        tmp.replace(target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def split_phrases(text):
    """Keep entire words while splitting only at semantic punctuation."""
    parts = [x.strip() for x in re.split(r"(?<=[,.!?;])\s+", str(text).strip()) if x.strip()]
    # No per-word chopping: tiny chunks sound unnatural.
    if not 1 <= len(parts) <= 24:
        raise ValueError("Narration has invalid phrase count")
    return parts


def join_phrases(parts, output):
    """Concatenate matching mono WAVs with bounded real acoustic pauses."""
    if not parts:
        raise ValueError("Missing speech phrases")
    output = Path(output)
    params = None
    with wave.open(str(output), "wb") as target:
        for idx, (path, phrase) in enumerate(parts):
            with wave.open(str(path), "rb") as audio:
                cur = (audio.getnchannels(), audio.getsampwidth(),
                       audio.getframerate(), audio.getcomptype())
                if idx == 0:
                    params = cur
                    if cur[0] != 1 or cur[1] != 2 or cur[3] != "NONE":
                        raise ValueError("Expected 16-bit mono Piper PCM")
                    target.setnchannels(1)
                    target.setsampwidth(2)
                    target.setframerate(cur[2])
                    # Lead-in silence prevents the first consonant from being clipped
                    # by TTS/decoder onset. Trailing silence preserves final syllable.
                    target.writeframes(b"\x00" * (int(cur[2] * 0.22) * cur[1]))
                elif cur != params:
                    raise ValueError("Piper sentence WAV formats disagree")
                target.writeframes(audio.readframes(audio.getnframes()))
            if idx < len(parts) - 1:
                gap = 0.27 if phrase.endswith((".", "!", "?")) else 0.15
                target.writeframes(b"\x00" * (int(params[2] * gap) * params[1]))
        target.writeframes(b"\x00" * (int(params[2] * 0.20) * params[1]))


def render(text, output, model_dir):
    text = str(text).strip()
    if not (25 <= len(text) <= 350):
        raise ValueError("Narration should contain 25-350 characters")
    if any(term in text.casefold() for term in ("хапыч", "эндуро")):
        raise ValueError("Disallowed channel branding in narration")
    model_dir = Path(model_dir)
    model = model_dir / STEM
    config = model_dir / (STEM + ".json")
    safe_download(BASE_URL + STEM, model, 60_000_000)
    if sha256(model) != MODEL_SHA256:
        model.unlink(missing_ok=True)
        raise RuntimeError("Voice model SHA256 does not match verified upstream")
    safe_download(BASE_URL + STEM + ".json", config, 3_000)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Synthesize complete clauses separately instead of feeding one uninterrupted
    # paragraph into VITS. This prevents sounds across a comma or a full stop
    # from collapsing into one another, then inserts real PCM silence.
    parts = split_phrases(text)
    output_files = []
    try:
        for index, phrase in enumerate(parts):
            part = output.with_name(output.stem + ".phrase-%02d.wav" % index)
            cmd = [
                sys.executable, "-m", "piper",
                "-m", str(model), "-f", str(part),
                "--length-scale", "1.18",
                "--sentence-silence", "0.00",
                "--noise-scale", "0.42",
                "--noise-w", "0.75",
                "--", phrase
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if result.returncode != 0 or not part.is_file():
                raise RuntimeError("Piper phrase generation failed: " + result.stderr[-950:])
            output_files.append((part, phrase))
        join_phrases(output_files, output)
    finally:
        for path, _ in output_files:
            path.unlink(missing_ok=True)
    if not output.is_file():
        raise RuntimeError("Voiceover WAV was not created")
    with wave.open(str(output), "rb") as inp:
        duration = inp.getnframes() / inp.getframerate()
        channels = inp.getnchannels()
    if channels != 1 or not (3.0 <= duration <= 35):
        raise RuntimeError(f"Voiceover duration/channels invalid: {duration:.2f}s / {channels}")
    print("VOICE_GENERATED", round(duration, 2), "seconds, CC0 dataset", flush=True)
    return duration


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--text", required=True)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--model-dir", required=True, type=Path)
    args = p.parse_args()
    render(args.text, args.output, args.model_dir)
