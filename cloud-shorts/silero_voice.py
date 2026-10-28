#!/usr/bin/env python3
"""Commercial-use Russian narration with Silero CIS Base, never NC models.

The exact permitted model is v5_cis_base_nostress, under MIT:
https://github.com/snakers4/silero-models/blob/master/LICENSE_CIS
Do not switch to v5_ru, v5_5_ru or v5_cis_ext without reviewing licenses.
"""
from __future__ import annotations
from pathlib import Path
import re
import wave

MODEL_ID = "v5_cis_base_nostress"
SPEAKER = "ru_zhadyra"
SAMPLE_RATE = 24000
LICENSE_NAME = "MIT"
UPSTREAM = "https://github.com/snakers4/silero-models"


def validate_voice(model_name=MODEL_ID, speaker=SPEAKER):
    if model_name != MODEL_ID or speaker != SPEAKER:
        raise ValueError("Only the audited MIT-licensed CIS Base voice is allowed")
    return True


def render(text, output, model_dir=None):
    """Generate one complete sentence-connected narration without word splitting.

    This model's native full-phrase inference tested with independent Whisper
    gave markedly higher coverage than the old Piper variant. Unlike Piper,
    per-clause splitting would make prosody and joins less natural.
    """
    validate_voice()
    text = str(text).strip()
    if not (25 <= len(text) <= 350):
        raise ValueError("Invalid Russian narration length")
    if re.search(r"(?:хапыч|эндуро)", text.casefold()):
        raise ValueError("Disallowed branding in narration")
    import numpy as np
    import torch
    from silero import silero_tts
    torch.set_num_threads(4)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    model, _ = silero_tts(language="ru", speaker=MODEL_ID)
    model.to(torch.device("cpu"))
    if SPEAKER not in set(model.speakers):
        raise RuntimeError("Expected MIT-licensed Russian speaker missing")
    data = model.apply_tts(text=text, speaker=SPEAKER, sample_rate=SAMPLE_RATE)
    arr = data.detach().cpu().numpy() if hasattr(data, "detach") else np.asarray(data)
    arr = np.asarray(arr, dtype=np.float32).reshape(-1)
    if not arr.size or not np.isfinite(arr).all():
        raise RuntimeError("Silero generated no usable PCM")
    # Small onset and release paddings prevent final syllables being lost in mux.
    pad = np.zeros(round(SAMPLE_RATE * 0.18), dtype=np.float32)
    arr = np.concatenate((pad, arr, pad))
    if float(np.max(np.abs(arr))) < 0.004:
        raise RuntimeError("Silero speech was effectively silent")
    duration = len(arr) / SAMPLE_RATE
    if not 3.0 <= duration <= 35.0:
        raise RuntimeError(f"Silero voice runtime {duration:.2f}s is outside Shorts limit")
    pcm = (np.clip(arr, -0.995, 0.995) * 32767).astype("<i2").tobytes()
    with wave.open(str(output), "wb") as dest:
        dest.setnchannels(1)
        dest.setsampwidth(2)
        dest.setframerate(SAMPLE_RATE)
        dest.writeframes(pcm)
    print("SILERO_MIT_RUSSIAN_VOICE_READY", round(duration, 2),
          "speaker", SPEAKER, "license", LICENSE_NAME, flush=True)
    return duration


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--text", required=True)
    p.add_argument("--output", type=Path, required=True)
    opts = p.parse_args()
    render(opts.text, opts.output)
