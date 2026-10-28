#!/usr/bin/env python3
"""Audition a commercially usable Silero CIS Base Russian voice (MIT only).

Does NOT publish or change the production TTS engine. The generated WAVs
are checked by an independent Russian ASR and returned for human review.
The non-commercial Silero v5_ru/v5_6_ru and CIS Ext are forbidden.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
import wave

from voice_qa import score
from tts_voice import render as old_render

MODEL_ID = "v5_cis_base_nostress"  # MIT-only model family
SPEAKER_TRIALS = ("ru_zhadyra", "ru_anatoliy")
SAMPLE_RATE = 24000


def dump_wav(wav_path, samples):
    import numpy as np
    x = samples.detach().cpu().numpy() if hasattr(samples, "detach") else np.asarray(samples)
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    if not x.size:
        raise RuntimeError("Silero returned empty speech")
    x = np.clip(x, -1, 1)
    pcm = (x * 32767).astype("<i2").tobytes()
    with wave.open(str(wav_path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(SAMPLE_RATE)
        target.writeframes(pcm)


def run_test(catalog, episode_id, out):
    import torch
    from silero import silero_tts
    from voice_qa import check
    torch.set_num_threads(4)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    chapters = json.loads(Path(catalog).read_text(encoding="utf8"))["episodes"]
    episode = next(x for x in chapters if x["id"] == episode_id)
    # Official silero-models README: this particular CIS base model is MIT.
    model, _ = silero_tts(language="ru", speaker=MODEL_ID)
    model.to(torch.device("cpu"))
    available = set(model.speakers)
    rows = {}
    for speaker in SPEAKER_TRIALS:
        if speaker not in available:
            rows[speaker] = {"passed": False, "error": "speaker_not_available"}
            continue
        dest = out / (speaker + ".wav")
        try:
            samples = model.apply_tts(text=episode["narration"], speaker=speaker,
                                      sample_rate=SAMPLE_RATE)
            dump_wav(dest, samples)
            result = check(episode, dest, model="base")
            rows[speaker] = result
            print("MIT_SILERO_VOICE",speaker,"lexical",result.get("lexical_coverage"),
                  "numeric",result.get("numerics_match"),
                  "passed",result.get("passed"),flush=True)
        except Exception as exc:
            rows[speaker] = {"passed": False, "error": type(exc).__name__, "detail": str(exc)[:210]}
            print("MIT_SILERO_VOICE_UNAVAILABLE",speaker,type(exc).__name__,flush=True)
    (out/"scores.json").write_text(
        json.dumps({"model": MODEL_ID, "license":"MIT",
                    "episode":episode_id, "samples":rows,
                    "note":"Audio/ASR are test evidence; human evaluation required. Production stays on Piper until confirmed."},
                   ensure_ascii=False,indent=2)+"\n",encoding="utf8")


if __name__ == "__main__":
    import argparse
    a=argparse.ArgumentParser()
    a.add_argument("--catalog",default="cloud-shorts/episodes.json")
    a.add_argument("--episode",default="elspeth-beard-s1-e01")
    a.add_argument("--out",default="cloud-shorts/dist/silero-mit")
    args=a.parse_args()
    run_test(args.catalog,args.episode,args.out)
