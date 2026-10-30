#!/usr/bin/env python3
"""GUSTAVA genuine deep Russian male studio narration, native timbre.

This is an MIT-licensed Silero V5 CIS Base male performer, NOT synthetic
pitched-down Kokoro Dima. Owner requested a clean bass-baritone. No growling,
no rubberband formant shifting, no doubled/panned narrators, no NC checkpoint.
"""
from __future__ import annotations
import hashlib,json,os,subprocess,wave
from pathlib import Path

from silero_voice import render as synthesize_silero,MODEL_ID,LICENSE_NAME
from voice_style import verify_pcm,sha256,profile_report_path

VOICE_ENGINE="silero_mit_bass_baritone"
PROFILE_ID="gustava_native_bass_baritone_v6"
SPEAKER="ru_alexandr"
SAMPLE_RATE=24000
FILTER=(
    "highpass=f=65,"
    "equalizer=f=245:t=q:w=1.0:g=-0.9,"
    "equalizer=f=2900:t=q:w=1.1:g=1.0,"
    "acompressor=threshold=0.17:ratio=1.55:attack=20:release=140,"
    "loudnorm=I=-19:TP=-2.5:LRA=8,"
    "alimiter=limit=0.94"
)

def validate_report(wav):
    path=profile_report_path(wav)
    if not path.is_file():
        raise ValueError("Native bass voice profile proof missing")
    data=json.loads(path.read_text(encoding="utf8"))
    if not (data.get("profile_id")==PROFILE_ID
            and data.get("speaker")==SPEAKER
            and data.get("source_model")==MODEL_ID
            and data.get("license")==LICENSE_NAME
            and data.get("pitch_shift")==1.0
            and data.get("quality_passed") is True
            and data.get("processed_wav_sha256")==sha256(wav)):
        raise ValueError("Native bass speaker identity or audio checksum mismatch")
    stats=verify_pcm(wav)
    if abs(stats["duration_seconds"]-float(data.get("audio",{}).get("duration_seconds",0)))>.01:
        raise ValueError("Native bass duration proof mismatch")
    return data

def render(text,output,model_dir=None,speed=1.0,ffmpeg="ffmpeg"):
    """Synthesize full original phrase in naturally low speaker voice."""
    speed=float(speed)
    if not .93<=speed<=1.08:
        raise ValueError("Unsafe baritone speech speed")
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    raw=output.with_name(output.stem+".native-raw.wav")
    temp=output.with_name(output.stem+".native-studio.tmp.wav")
    profile=profile_report_path(output)
    profile.unlink(missing_ok=True)
    try:
        duration=synthesize_silero(text,raw,model_dir,speaker=SPEAKER)
        checked=verify_pcm(raw)
        graph=FILTER+",atempo=%.3f"%speed
        result=subprocess.run(
            [ffmpeg,"-hide_banner","-nostdin","-loglevel","error","-y",
             "-i",str(raw),"-af",graph,"-vn","-ar","24000",
             "-ac","1","-c:a","pcm_s16le",str(temp)],
            text=True,capture_output=True,timeout=140)
        if result.returncode!=0 or not temp.is_file():
            raise RuntimeError("Native baritone studio filtering failed: "+result.stderr[-400:])
        clean=verify_pcm(temp)
        if abs(clean["duration_seconds"]-checked["duration_seconds"]/speed)>.45:
            raise RuntimeError("Native baritone TTS duration/timing corrupted")
        temp.replace(output)
        proof={"profile_id":PROFILE_ID,"speaker":SPEAKER,"source_model":MODEL_ID,
               "license":LICENSE_NAME,"pitch_shift":1.0,
               "studio_processing":"clean_original_actor_without_pitch_shift",
               "one_mono_voice_only":True,"quality_passed":True,
               "processed_wav_sha256":sha256(output),"audio":clean,
               "disclaimer":"Digital signal checks do not replace listening for naturalness."}
        profile.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
        validate_report(output)
        print("NATIVE_REAL_BASS_BARITONE_READY",PROFILE_ID,SPEAKER,
              "seconds",clean["duration_seconds"],"rms",clean["rms_dbfs"],flush=True)
        return clean["duration_seconds"]
    finally:
        raw.unlink(missing_ok=True)
        temp.unlink(missing_ok=True)
