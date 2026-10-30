#!/usr/bin/env python3
"""CPU-only, rights-checked Russian male TTS from licensed Kokoro-RU.

Produces fresh narration for every story using the same recognisable narrator.
The model is OpenRAIL (check permitted uses before deployment). Not a real
person recording: do not present synthetic speech as a named human actor.
"""
from __future__ import annotations
from pathlib import Path
from voice_style import apply as deepen_male_voice, PROFILE_ID as MALE_STYLE
import os
import re
import sys
import time

MODEL_REPO="zaakirio/kokoro-ru"
SPEAKER="dima"
MODEL_FILE="kokoro-ru-v2-dima.pth"
VOICE_FILE="voices/dima.pt"
MODEL_CARD="https://huggingface.co/zaakirio/kokoro-ru"
CHECKPOINT_SHA256="658ae47e24224257ea9f83c88ea7743c5c9f0922c6bc339805ffebcfdbcb2b24"


def validate_text(text: str) -> str:
    text=str(text).strip()
    if not 25 <= len(text) <= 350:
        raise ValueError("Russian narration should have 25-350 characters")
    if not re.search(r"[а-яё]",text,re.I):
        raise ValueError("Missing Russian Cyrillic text")
    if re.search(r"(?:хапыч|эндуро)",text,re.I):
        raise ValueError("Forbidden brand names in short narration")
    if len(re.split(r"(?<=[.!?])\s+",text)) > 12:
        raise ValueError("More than 12 segments harms narrator continuity")
    return text


def render(text, output, model_dir=None, speed=1.0, apply_style=True):
    """Render full phrase with bounded sentence breaks, 24 kHz WAV.

    Downloads pinned upstream voice model and bundled Russian espeak dictionary
    into a *private* local/cache directory; never embeds AI model in Git repo.
    """
    text=validate_text(text)
    speed=float(speed)
    if not .92 <= speed <= 1.08:
        raise ValueError("Unapproved synthetic speech speed")
    os.environ.setdefault("HF_HUB_DISABLE_XET","1")
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT","60")
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT","30")
    os.environ.setdefault("PYTHONUTF8","1")
    import hashlib
    import numpy as np
    import soundfile as sf
    import torch
    from huggingface_hub import snapshot_download
    from kokoro import KModel

    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    destination=Path(model_dir) if model_dir else output.parent / "kokoro_model"
    destination.mkdir(parents=True,exist_ok=True)
    snapshot_download(
        repo_id=MODEL_REPO,local_dir=str(destination),
        allow_patterns=[MODEL_FILE,VOICE_FILE,"ru_g2p.py",
                        "kokoro-config.json","espeak-data/**"],
        max_workers=5,
    )
    checkpoint=destination / MODEL_FILE
    voicepack=destination / VOICE_FILE
    if not checkpoint.is_file() or not voicepack.is_file():
        raise RuntimeError("Incomplete Kokoro-RU male model or voicepack")
    sha=hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    if sha != CHECKPOINT_SHA256:
        raise RuntimeError("Kokoro-RU voice model failed pinned SHA-256 check")
    from importlib.util import module_from_spec,spec_from_file_location
    # Import uniquely by absolute path so other projects' text preprocessors
    # never shadow the bundled Russian stress/phonemizer implementation.
    spec=spec_from_file_location("_gustava_ru_g2p",destination/"ru_g2p.py")
    module=module_from_spec(spec)
    spec.loader.exec_module(module)
    g2p=module.RuG2P()
    model=KModel(repo_id=MODEL_REPO,model=str(checkpoint)).eval()
    pack=torch.load(str(voicepack),map_location="cpu",weights_only=False)
    parts=[]
    for sentence in re.split(r"(?<=[.!?])\s+",text):
        if not sentence.strip():
            continue
        phonemes,oov=g2p(sentence)
        if oov or len(phonemes)<4 or len(phonemes)>510:
            raise RuntimeError("Russian phonemes too long or invalid")
        with torch.inference_mode():
            output_audio=model(phonemes,pack[len(phonemes)-1],speed,return_output=True).audio
        data=output_audio.detach().cpu().numpy().astype("float32")
        if not len(data) or not np.isfinite(data).all():
            raise RuntimeError("Speech model returned invalid audio")
        parts.append(data)
        parts.append(np.zeros(round(.13*24000),dtype="float32"))
    if not parts:
        raise RuntimeError("No spoken samples generated")
    audio=np.concatenate([np.zeros(round(.12*24000),dtype="float32"),*parts])
    duration=len(audio)/24000
    if not 3.0<=duration<=35.0:
        raise RuntimeError("Narration outside Shorts duration: %.2fs" % duration)
    if np.max(np.abs(audio)) < .01:
        raise RuntimeError("Narration is effectively silent")
    sf.write(str(output), audio, 24000, subtype="PCM_16")
    # Always apply one AND ONLY ONE low-male voice style after raw synthesis.
    # Never add a second narration layer or pan voices across speakers.
    if not apply_style:
        # Raw reference is for a three-way comparative audition ONLY.
        print("KOKORO_RU_RAW_STUDIO_REFERENCE",round(duration,2),"seconds",flush=True)
        return duration
    deep_duration = deepen_male_voice(output)
    print("KOKORO_RU_BASS_BARITONE_READY", round(deep_duration, 2),
          "seconds", SPEAKER, "profile", MALE_STYLE,
          "speed", speed, "license=OpenRAIL", flush=True)
    return deep_duration
