#!/usr/bin/env python3
"""Language and audio safety gate for Russian Shorts narration.

Automated tests can reject inaudible/damaged narration but CANNOT verify that
speech feels human. Human approval of the narrator/style is a separate gate.
No disclosure of a voice being synthetic is removed by this validator.
"""
import argparse
from array import array
import difflib
import json
import math
from pathlib import Path
import re
import subprocess


def words(s):
    return re.findall(r"[a-zа-я0-9]+",str(s or "").lower().replace("ё","е"))


def compare_text(expected, recognized):
    a,b=words(expected),words(recognized)
    blocks=difflib.SequenceMatcher(None,a,b,autojunk=False).get_matching_blocks()
    matched=sum(x.size for x in blocks)
    suffix=a[-4:] if len(a)>=4 else a
    return {"lexical_coverage":matched/max(1,len(a)),
            "expected_words":len(a),"heard_words":len(b),
            "last_four_present":len(suffix)>=1 and len(b)>=len(suffix) and b[-len(suffix):]==suffix}


def audio_features(filename, ffmpeg="ffmpeg"):
    command=[ffmpeg,"-hide_banner","-loglevel","error","-i",str(filename),
             "-vn","-ac","1","-ar","16000","-f","s16le","-"]
    p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=65)
    if p.returncode:
        raise RuntimeError("Audio decode failed: "+p.stderr.decode("utf8","replace")[-400:])
    samples=array("h")
    samples.frombytes(p.stdout[:len(p.stdout)//2*2])
    if len(samples)<16000:
        raise ValueError("Narration is shorter than 1 second or contains no PCM")
    clipped=sum(1 for x in samples if abs(x)>=32600)/len(samples)
    rms=(sum((x/32768)**2 for x in samples)/len(samples))**0.5
    peak=max(abs(x) for x in samples)/32768
    # Count internal continuous low-volume gaps, not start/end fades.
    threshold=max(65,int(max(abs(x) for x in samples)*.015))
    active=[i for i,x in enumerate(samples) if abs(x)>threshold]
    if not active:
        raise ValueError("Decoded track is effectively silent")
    start,end=active[0],active[-1]
    silent=0
    longest=0
    for x in samples[start:end+1]:
        if abs(x)<=threshold:
            silent+=1
        else:
            longest=max(longest,silent)
            silent=0
    longest=max(longest,silent)
    return {"duration_seconds":len(samples)/16000,"clipped_fraction":clipped,
            "rms_dbfs":20*math.log10(max(rms,1e-10)),
            "peak_dbfs":20*math.log10(max(peak,1e-10)),
            "longest_interior_quiet_gap_seconds":longest/16000}


def check(expected,asr,audio,approved_style=False,features=None):
    text=compare_text(expected,asr)
    sound=features if features is not None else audio_features(audio)
    errors=[]
    warnings=[]
    if text["lexical_coverage"]<.97:
        errors.append("RECOGNITION_BELOW_97_PERCENT")
    if not text["last_four_present"]:
        errors.append("ENDING_MISSING_OR_WRONG")
    if sound["clipped_fraction"]>.001:
        errors.append("DIGITAL_CLIPPING")
    if sound["duration_seconds"]<2 or sound["duration_seconds"]>180:
        errors.append("UNEXPECTED_DURATION")
    if sound["rms_dbfs"]< -37:
        errors.append("LOW_NARRATION_LEVEL")
    if sound["longest_interior_quiet_gap_seconds"]>1.3:
        warnings.append("LONG_INTERNAL_PAUSE_REVIEW")
    wpm=text["heard_words"]/(sound["duration_seconds"]/60)
    if wpm>188:
        warnings.append("RUSHED_SPEECH_REVIEW")
    if wpm<100:
        warnings.append("SLOW_SPEECH_REVIEW")
    if not approved_style:
        errors.append("HUMAN_NATURALNESS_APPROVAL_MISSING")
    return {"publish_allowed":not errors,
            "human_approved_style":bool(approved_style),
            "text":text,"audio":sound,"words_per_minute":round(wpm,1),
            "hard_errors":errors,"review_warnings":warnings,
            "limitations":"ASR and audio levels cannot prove natural prosody, human identity, emotional expression, accent or audience acceptance."}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--audio",type=Path,required=True)
    p.add_argument("--expected-text-file",type=Path,required=True)
    p.add_argument("--recognized-text-file",type=Path,required=True)
    p.add_argument("--approved-style",action="store_true",
                   help="Use ONLY after real listening comparison and approval")
    p.add_argument("--out",type=Path,default=Path("voice-quality.json"))
    a=p.parse_args()
    result=check(a.expected_text_file.read_text("utf8"),
                 a.recognized_text_file.read_text("utf8"),a.audio,a.approved_style)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False),"utf8")
    print(json.dumps({"publish_allowed":result["publish_allowed"],
                      "errors":result["hard_errors"],"warnings":result["review_warnings"],
                      "lexical_coverage":round(result["text"]["lexical_coverage"],3)}))
    raise SystemExit(0 if result["publish_allowed"] else 2)


if __name__=="__main__":
    main()
