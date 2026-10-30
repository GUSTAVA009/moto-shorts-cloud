#!/usr/bin/env python3
"""Audition several authentic MIT-licensed Russian male actors for GUSTAVA.

An explicit replacement for silently reusing ru_alexandr on every Short.
Not a voice-clone of a YouTube creator. Do NOT publish one without a
human listening comparison and independent ASR on the selected performer.
"""
from __future__ import annotations
from pathlib import Path
from array import array
import json
import math
import subprocess
import wave

MODEL="v5_cis_base_nostress"
SAMPLE_RATE=24000
LICENSE="MIT"
# All are distinct Russian voices within the same audited MIT CIS base.
MALE_CANDIDATES=(
    "ru_bogdan", "ru_dmitriy", "ru_igor", "ru_marat",
    "ru_roman", "ru_eduard", "ru_alexandr",
)
TEXT=("Никогда не угадаешь, почему на этой дороге так важно тормозить заранее. "
      "Перед поворотом райдер снижает скорость и выбирает безопасную траекторию. "
      "Сначала контроль, потом скорость. А ты как поступаешь?")


def median_pitch(samples, sample_rate=SAMPLE_RATE):
    """Robust rough F0 from short 80-ms autocorrelation windows, not a voice rating."""
    import numpy as np
    a=np.asarray(samples,dtype=np.float64)
    n=2048
    minlag=round(sample_rate/220)
    maxlag=round(sample_rate/65)
    pitches=[]
    for start in range(0,max(1,len(a)-n),sample_rate//4):
        frame=a[start:start+n]
        if frame.size!=n:
            continue
        frame=frame-np.mean(frame)
        rms=np.sqrt(np.mean(frame*frame))
        if rms < .025:
            continue
        # FFT autocorrelation, O(n log n), safe for CI CPU runners.
        spectrum=np.fft.rfft(frame*np.hanning(n),n=2*n)
        corr=np.fft.irfft(spectrum*np.conj(spectrum),n=2*n)[:n]
        norm=corr[0]
        if norm<=1e-8:
            continue
        lag=minlag+int(np.argmax(corr[minlag:maxlag+1]))
        if corr[lag]/norm >= .37:
            pitches.append(sample_rate/lag)
    if len(pitches)<4:
        return None
    return round(float(np.median(pitches)),1)


def assess(wav):
    """Signal-level evidence; 'pleasant / brutal voice' needs a human listener."""
    import numpy as np
    with wave.open(str(wav),"rb") as f:
        if (f.getnchannels(),f.getframerate(),f.getsampwidth())!=(1,SAMPLE_RATE,2):
            raise ValueError("Expected mono 24-kHz PCM")
        pcm=np.frombuffer(f.readframes(f.getnframes()),dtype="<i2").astype("float32")/32768.
    if len(pcm)<SAMPLE_RATE*4:
        raise ValueError("Voice is too short")
    clipped=float(np.mean(np.abs(pcm)>=.999))
    if clipped>.001:
        raise ValueError("Audition contains digital clipping")
    return {"seconds":round(len(pcm)/SAMPLE_RATE,2),
            "pitch_median_hz":median_pitch(pcm),
            "rms_dbfs":round(20*math.log10(max(1e-7,float(np.sqrt(np.mean(pcm*pcm))))),1),
            "clipped_fraction":round(clipped,6)}


def create(outdir):
    import numpy as np
    import torch
    from silero import silero_tts
    torch.set_num_threads(4)
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    model,_=silero_tts(language="ru",speaker=MODEL)
    model.to(torch.device("cpu"))
    candidates=set(model.speakers)
    missing=set(MALE_CANDIDATES)-candidates
    if missing:
        raise RuntimeError("MIT CIS Base voice missing: "+", ".join(sorted(missing)))
    results=[]
    for speaker in MALE_CANDIDATES:
        # One raw source, one whole narration; never splice fragments
        signal=model.apply_tts(text=TEXT,speaker=speaker,sample_rate=SAMPLE_RATE)
        audio=np.asarray(signal.detach().cpu().numpy(),dtype="float32")
        pad=np.zeros(round(.12*SAMPLE_RATE),dtype="float32")
        audio=np.concatenate((pad,audio,pad))
        audio=np.clip(audio,-.99,.99)
        destination=root/(speaker+".wav")
        with wave.open(str(destination),"wb") as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(SAMPLE_RATE)
            f.writeframes((audio*32767).astype("<i2").tobytes())
        measurement=assess(destination)
        subprocess.run(["ffmpeg","-hide_banner","-nostdin","-loglevel","error","-y",
                        "-i",str(destination),"-codec:a","libmp3lame","-q:a","3",
                        str(root/(speaker+".mp3"))],check=True,timeout=70)
        results.append({"speaker":speaker,"license":LICENSE,**measurement})
        print("REAL_MALE_VOICE_AUDITION",speaker,json.dumps(measurement),flush=True)
    (root/"voice_comparison.json").write_text(
        json.dumps({"model":MODEL,"license":LICENSE,"text":TEXT,
                    "results":results,"automatic_voice_approval":False,
                    "note":"F0 is not pleasantness. Listen to all candidates before releasing a speaker."},
                   ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print("SEVEN_REAL_VOICES_READY_FOR_LISTENING",flush=True)


if __name__=="__main__":
    create("cloud-shorts/dist/new-bass-casting")
