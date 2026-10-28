#!/usr/bin/env python3
"""Offline-on-runner A/B Russian TTS voice comparison, never publishes video.

Use only verified commercial-usable CC0 Piper voices, run independent Whisper
on the same exact script, and save WAV+JSON for audible editorial QA.
"""
from __future__ import annotations
import json
from pathlib import Path
import tts_voice as t
import voice_qa as qa

VOICES = {
    "dmitri": {
        "BASE_URL": "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/dmitri/medium/",
        "STEM": "ru_RU-dmitri-medium.onnx",
        "MODEL_SHA256": "f073356ebc4bd0f80c5af58df2953a5988bd5bdab1eb38635ce960b071fbefcb"
    },
    "denis": {
        "BASE_URL": "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/denis/medium/",
        "STEM": "ru_RU-denis-medium.onnx",
        "MODEL_SHA256": "15fab56e11a097858ee115545d0f697fc2a316c41a291a5362349fb870411b0a"
    },
}

def compare(catalog, slug, target):
    episodes = json.loads(Path(catalog).read_text(encoding="utf8"))["episodes"]
    ep = next(e for e in episodes if e["id"] == slug)
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    results = {}
    original = {k:getattr(t,k) for k in ("BASE_URL","STEM","MODEL_SHA256")}
    for name, opts in VOICES.items():
        for key,value in opts.items(): setattr(t,key,value)
        wav = target / (name+".wav")
        try:
            t.render(ep["narration"], wav, target / ("model_"+name))
            result=qa.check(ep,wav,model="base")
            results[name] = result
            print("VOICE_CANDIDATE",name,"lexical",result.get("lexical_coverage"),
                  "first",result.get("beginning_coverage"),
                  "last",result.get("ending_coverage"),
                  "passed",result.get("passed"),flush=True)
        except Exception as exc:
            results[name] = {"passed":False,"reason":type(exc).__name__+":"+str(exc)[:180]}
            print("VOICE_CANDIDATE_UNAVAILABLE",name,type(exc).__name__,flush=True)
    for key,value in original.items(): setattr(t,key,value)
    (target / "scores.json").write_text(json.dumps(
        {"episode":slug, "results":results, "note":"Compare perceptual quality by ear before switching production voice."},
        ensure_ascii=False,indent=2)+"\n", encoding="utf8")


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--episode",default="elspeth-beard-s1-e01")
    p.add_argument("--catalog",default="cloud-shorts/episodes.json")
    p.add_argument("--out",default="cloud-shorts/dist/voice-ab")
    a=p.parse_args()
    compare(a.catalog,a.episode,a.out)
