#!/usr/bin/env python3
"""Audition genuinely different MIT-licensed natural male CIS voices.

No cloning, no non-commercial checkpoints, no harsh pitch shift. Not a
publishing or replacement-of-voice task until the listener approves one.
"""
from __future__ import annotations
import math,subprocess
import wave
from pathlib import Path
from array import array

MODEL_ID="v5_cis_base_nostress"
LICENSE="MIT"
CANDIDATES=("ru_eduard","ru_alexandr")
SAMPLE_RATE=24000
TEST_TEXT=("Вечером город затихает, но дорога продолжает жить. "
           "Мотоцикл проходит поворот уверенно и спокойно. "
           "Каждое слово должно звучать чётко. "
           "Настоящая сила голоса — в спокойствии и уверенности.")


def check_choice(model_id,speaker):
    if model_id!=MODEL_ID:
        raise ValueError("Only licensed MIT CIS Base is allowed")
    if speaker not in CANDIDATES:
        raise ValueError("Unreviewed or non-male voice not allowed")
    return True


def write_pcm(audio,path):
    import numpy as np
    source=audio.detach().cpu().numpy() if hasattr(audio,"detach") else np.asarray(audio)
    samples=np.asarray(source,dtype=np.float32).reshape(-1)
    if not samples.size or not np.isfinite(samples).all():
        raise RuntimeError("Silero returned invalid audio")
    duration=len(samples)/SAMPLE_RATE
    if not 3.0<=duration<=35.0:
        raise RuntimeError("Audio outside Shorts duration")
    if np.max(np.abs(samples))<.015:
        raise RuntimeError("Silero voice is too quiet")
    pad=np.zeros(round(.20*SAMPLE_RATE),dtype=np.float32)
    samples=np.concatenate((pad,samples,pad))
    samples=np.clip(samples,-0.985,0.985)
    pcm=(samples*32767).astype("<i2").tobytes()
    with wave.open(str(path),"wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm)
    return duration


def audition(directory):
    import torch
    from silero import silero_tts
    import numpy as np
    torch.set_num_threads(4)
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    model,_=silero_tts(language="ru",speaker=MODEL_ID)
    model.to(torch.device("cpu"))
    choices=set(model.speakers)
    for speaker in CANDIDATES:
        check_choice(MODEL_ID,speaker)
        if speaker not in choices:
            raise RuntimeError("Required MIT speaker not present: "+speaker)
        original=directory/(speaker+"_dry.wav")
        write_pcm(model.apply_tts(text=TEST_TEXT,speaker=speaker,
                                   sample_rate=SAMPLE_RATE),original)
        wav=directory/(speaker+"_clean.wav")
        mp3=directory/(speaker+"_clean.mp3")
        # No rubberband/pitch shift: preserve the speaker's actual bass timbre.
        filt=("highpass=f=65,equalizer=f=245:t=q:w=1.0:g=-0.9,"
              "equalizer=f=2900:t=q:w=1.1:g=1.0,"
              "acompressor=threshold=0.17:ratio=1.55:attack=20:release=140,"
              "loudnorm=I=-19:TP=-2.5:LRA=8,alimiter=limit=0.94")
        subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y",
          "-i",str(original),"-af",filt,"-ar",str(SAMPLE_RATE),
          "-ac","1","-c:a","pcm_s16le",str(wav)],check=True,timeout=120)
        subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y",
          "-i",str(wav),"-codec:a","libmp3lame","-q:a","3",str(mp3)],
          check=True,timeout=45)
        if not mp3.is_file() or mp3.stat().st_size<40_000:
            raise RuntimeError("Audition MP3 was not rendered")
        print("REAL_BASS_BARITONE_SPEAKER_AUDITION_READY",speaker,
              "bytes",mp3.stat().st_size,flush=True)
        original.unlink(missing_ok=True)
    (directory/"README.txt").write_text(
        "Two naturally different male source voices on MIT-licensed "
        "v5_cis_base_nostress. No artificial pitch shift. "
        "Test text:\\n"+TEST_TEXT+"\\n",encoding="utf8")


if __name__=="__main__":
    audition(Path("silero_audition"))
