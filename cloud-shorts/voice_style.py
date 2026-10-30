#!/usr/bin/env python3
"""Studio bass-baritone v5 for Russian motorcycle Shorts.

One licensed Russian male Kokoro Dima voice. No invented voice-cloning claim.
Three listener-comparable registers are synthesized from the SAME ORIGINAL
24-kHz studio recording, not iteratively lowering an already shifted WAV.
Low-frequency rumble, saturation, artificial rasp and doubled voice: forbidden.
This processing is not proof that human listeners perceive a natural baritone.
"""
from __future__ import annotations
import argparse
from array import array
import hashlib
import json
from math import log10, sqrt
from pathlib import Path
import subprocess
import wave

SPEAKER="dima"
MODEL="zaakirio/kokoro-ru"
SAMPLE_RATE=24000
MIN_SECONDS=3.0
MAX_SECONDS=35.0

# Audition each register BEFORE claiming the user's requested timbre is met.
VOICE_PRESETS = {
    "baritone":       ("gustava_male_baritone_clean_v5", 0.92),
    "bass_baritone":  ("gustava_male_bass_baritone_v5", 0.87),
    "deep_bass":      ("gustava_male_deep_bass_clean_v5", 0.83),
}
DEFAULT_PRESET="bass_baritone"
PROFILE_ID,PITCH=VOICE_PRESETS[DEFAULT_PRESET]


def filter_for(pitch):
    if not 0.80 <= pitch <= 0.96:
        raise ValueError("Deep voice preset outside safe, tested pitch range")
    return (
        f"rubberband=pitch={pitch:.2f}:formant=preserved:transients=smooth:"
        "detector=soft:window=long:smoothing=on:pitchq=quality,"
        "highpass=f=72,"
        "equalizer=f=120:t=q:w=0.8:g=0.9,"
        "equalizer=f=235:t=q:w=1.0:g=-1.7,"
        "equalizer=f=3000:t=q:w=1.2:g=1.7,"
        "acompressor=threshold=0.16:ratio=1.65:attack=20:release=145:makeup=1.05,"
        "loudnorm=I=-19:LRA=8:TP=-2.5,"
        "alimiter=limit=0.94"
    )


FILTER=filter_for(PITCH)


def verify_pcm(wav):
    """Reject loss of duration, silence, digital clipping and stereo doubled voice."""
    with wave.open(str(wav),"rb") as f:
        channels,width,rate,n=f.getnchannels(),f.getsampwidth(),f.getframerate(),f.getnframes()
        if channels!=1 or width!=2 or rate!=SAMPLE_RATE:
            raise ValueError("Narration must be 24kHz 16bit mono PCM")
        duration=n/float(rate)
        if not MIN_SECONDS<=duration<=MAX_SECONDS:
            raise ValueError("Narration duration outside 3-35 seconds")
        pcm=array("h")
        pcm.frombytes(f.readframes(n))
    if not pcm:
        raise ValueError("Narration PCM empty")
    peak=max(abs(x) for x in pcm)/32768.
    rms=sqrt(sum((x/32768.)**2 for x in pcm)/len(pcm))
    clipping=sum(abs(x)>=32700 for x in pcm)/len(pcm)
    if peak<.012 or rms<.007:
        raise ValueError("Narration has too little sound")
    if peak>.995 or clipping>.001:
        raise ValueError("Narration digitally clipped")
    return {"duration_seconds":round(duration,3),
            "peak_dbfs":round(20*log10(peak),2),
            "rms_dbfs":round(20*log10(rms),2),
            "clipped_fraction":round(clipping,6)}


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def profile_report_path(wav):
    return Path(wav).with_suffix(".profile.json")


def validate_report(wav, expected_profile=PROFILE_ID):
    report=profile_report_path(wav)
    if not report.is_file():
        raise ValueError("Bass-baritone voice-profile proof missing")
    obj=json.loads(report.read_text(encoding="utf8"))
    permitted={v[0]:v[1] for v in VOICE_PRESETS.values()}
    if expected_profile not in permitted:
        raise ValueError("Unknown approved voice preset")
    if obj.get("profile_id")!=expected_profile or obj.get("speaker")!=SPEAKER:
        raise ValueError("Unapproved voice/speaker")
    if (obj.get("pitch")!=permitted[expected_profile] or
            obj.get("formants")!="preserved" or
            obj.get("processed_wav_sha256")!=sha256(wav)):
        raise ValueError("Voice processing checksum or settings mismatch")
    stats=verify_pcm(wav)
    if abs(float(obj.get("audio",{}).get("duration_seconds",0))-
           stats["duration_seconds"])>.01:
        raise ValueError("Voice-profile duration mismatch")
    if obj.get("quality_passed") is not True:
        raise ValueError("Voice-profile digital QA did not pass")
    return obj


def apply(wav,ffmpeg="ffmpeg",preset=DEFAULT_PRESET):
    """One clean DSP pass, keep entire Russian phrase coherent and mono."""
    if preset not in VOICE_PRESETS:
        raise ValueError("Unknown baritone preset")
    profile_id,pitch=VOICE_PRESETS[preset]
    wav=Path(wav)
    before=verify_pcm(wav)
    temp=wav.with_name(wav.stem+".studio-baritone.tmp.wav")
    report=profile_report_path(wav)
    report.unlink(missing_ok=True)
    try:
        result=subprocess.run([
            ffmpeg,"-hide_banner","-nostdin","-loglevel","error","-y",
            "-i",str(wav),"-vn","-af",filter_for(pitch),
            "-ac","1","-ar",str(SAMPLE_RATE),"-c:a","pcm_s16le",str(temp)
        ],capture_output=True,text=True,timeout=130)
        if result.returncode!=0 or not temp.is_file():
            raise RuntimeError("FFmpeg clean baritone processing failed: "+result.stderr[-480:])
        after=verify_pcm(temp)
        if abs(after["duration_seconds"]-before["duration_seconds"])>.30:
            raise RuntimeError("Voice processing changed words or speech timing")
        temp.replace(wav)
        proof={
            "profile_id":profile_id,"preset":preset,"speaker":SPEAKER,
            "source_model":MODEL,"pitch":pitch,"formants":"preserved",
            "synthesized_voice_only":True,
            "timbre_processing":"clean_centered_bass_baritone_v5",
            "saturation":False,"vocal_stereo_layers":1,
            "quality_passed":True,"processed_wav_sha256":sha256(wav),
            "audio":after,
            "disclaimer":"Signal QA is not listener approval or proof of bass-baritone voice identity."
        }
        report.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
        validate_report(wav,expected_profile=profile_id)
        print("GUSTAVA_CLEAN_BARITONE_READY",profile_id,"pitch",pitch,
              "rms_dbfs",after["rms_dbfs"],flush=True)
        return after["duration_seconds"]
    finally:
        temp.unlink(missing_ok=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--wav",type=Path,required=True)
    p.add_argument("--preset",choices=tuple(VOICE_PRESETS),default=DEFAULT_PRESET)
    p.add_argument("--check-only",action="store_true")
    args=p.parse_args()
    pid=VOICE_PRESETS[args.preset][0]
    if args.check_only:
        print("GUSTAVA_MALE_PROFILE_VERIFIED",validate_report(args.wav,pid)["profile_id"])
    else:
        apply(args.wav,preset=args.preset)


if __name__=="__main__":
    main()
