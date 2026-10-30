#!/usr/bin/env python3
"""Original lightweight sound design, NOT copyrighted songs or stock SFX.

Use subtle transitional cues only. A discrete mono voice is mixed separately,
so sound effects never duplicate or move narration between channels.
"""
from __future__ import annotations
from array import array
import math
from pathlib import Path
import random
import wave

SAMPLE_RATE=32000
VALID_STYLES={"action","night-drive","garage-groove","race-breakbeat","desert-cinematic"}


def create(path,seconds,style="action",seed=0,sample_rate=SAMPLE_RATE):
    duration=float(seconds)
    if not 7.0<=duration<=37.0 or style not in VALID_STYLES or not 3000<=sample_rate<=48000:
        raise ValueError("Invalid soundtrack cue context")
    n=math.ceil(duration*sample_rate)
    signal=array("f",[0.0])*n
    rng=random.Random(int(seed))
    times=[]
    # 0-second hook and sparse accents matching original scene cuts. Not an
    # endless same-tempo, every-cut template: type and placement vary by seed.
    for i in range(min(5,int(duration/2.4)+1)):
        time=0.08 if i==0 else 2.15*i + rng.uniform(-.22,.24)
        if time>=duration-.7:
            continue
        times.append(round(time,2))
        start=int(time*sample_rate)
        count=min(int((.24 if i==0 else .18)*sample_rate),n-start)
        if count<=0:
            continue
        tone=54+(int(seed)+i*17)%35
        damp=8.0 if i==0 else 15.0
        # New source sample each episode: low transient plus soft band-limited
        # whoosh, quieter for garage and documentary than racing.
        gain=0.16 if i==0 else 0.10
        if style=="garage-groove":
            gain*=.65
        elif style=="race-breakbeat":
            gain*=1.2
        noise_memory=0.0
        phase=0.0
        for j in range(count):
            t=j/sample_rate
            u=j/max(1,count-1)
            phase+=2*math.pi*(tone+35*math.exp(-t*24))/sample_rate
            noise_memory=.88*noise_memory+.12*rng.uniform(-1,1)
            envelope=math.sin(math.pi*u)**2
            tonal=math.sin(phase)*math.exp(-t*damp)
            whoosh=noise_memory*envelope*(.65 if i==0 else .45)
            signal[start+j]+=gain*(tonal*.8+whoosh)
    peak=max(abs(x) for x in signal)
    if peak<=0:
        raise RuntimeError("No original sound accents")
    scale=min(1.0,.42/peak)
    out=array("h",(round(max(-.9,min(.9,x*scale))*32767) for x in signal))
    destination=Path(path)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(destination),"wb") as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(sample_rate)
        f.writeframes(out.tobytes())
    return {"events_seconds":times,"samples":n,"peak":round(peak*scale,3),
            "stereo_voice_doubled":False,"original_synthesized_effects":True}


def cover_times(total):
    """Three reproducible meaningful frames from the OWN finished MP4."""
    t=float(total)
    if not 7.0<=t<=37.0:
        raise ValueError("Invalid Shorts duration for cover")
    return [round(max(.2,min(t-.5,f*t)),2) for f in (.10,.37,.68)]
