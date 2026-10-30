#!/usr/bin/env python3
"""Safely ingest exact approved AI Doc Maker Deep assets from the GitHub inbox.

Does not generate a voice, synthesize a fallback, or auto-publish unverified
audio. Unavailable sources are a hard failure, not a silent "success".
"""
from __future__ import annotations
import base64, hashlib, json, os, re, subprocess, sys, tempfile, urllib.request
from pathlib import Path
from deep_voice import approved_asset, pcm_stats, ready, VOICE_ENGINE, PROFILE_ID
from voice_qa import score
from asr_fallback import transcribe
from autofill_catalog import github
from render_episode import validate_episode
from editorial_guard import validate_catalog

CATALOG="cloud-shorts/episodes.json"
INBOX=Path(__file__).with_name("deep-voice-inbox.json")
MAX_RECORDS=10

def digest(data): return hashlib.sha256(data).hexdigest()

def assert_candidate(record, episode):
    if record["episode_id"] != episode["id"]:
        raise ValueError("Episode mismatch in DEEP inbox")
    if episode.get("voice_engine") != VOICE_ENGINE:
        raise ValueError("Refusing to insert DEEP into another engine")
    text=record.get("narration","")
    if not isinstance(text,str) or not 125<=len(text)<=350:
        raise ValueError("Invalid DEEP transcript length")
    if record.get("voice_id")!="deep" or record.get("provider")!="aidocmaker.com":
        raise ValueError("Unapproved voice")
    meta={"provider":record["provider"],"voice_id":record["voice_id"],
          "preview_url":record["preview_url"],
          "transcript_sha256":digest(text.encode("utf-8"))}
    approved_asset(meta,text)
    return meta

def assess(record, episode, folder):
    meta=assert_candidate(record,episode)
    url=meta["preview_url"]
    req=urllib.request.Request(url,headers={"User-Agent":"GUSTAVA-DEEP-QA/1.0"})
    with urllib.request.urlopen(req,timeout=50) as r:
        if r.geturl()!=url:
            raise RuntimeError("DEEP source redirected")
        mp3=r.read(6_000_001)
    if not 20_000<=len(mp3)<=6_000_000 or not (
        mp3.startswith(b"ID3") or (mp3[0]==255)):
        raise ValueError("Invalid provider audio")
    with tempfile.TemporaryDirectory(dir=folder) as td:
        raw=Path(td)/"deep.mp3";wav=Path(td)/"deep.wav"
        raw.write_bytes(mp3)
        subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error",
                        "-y","-i",str(raw),"-ar","24000","-ac","1",
                        "-c:a","pcm_s16le",str(wav)],
                       check=True,timeout=90)
        audio=pcm_stats(wav)
        heard,engine=transcribe(wav,model="small")
        qa=score(record["narration"],heard)
        if qa["passed"] is not True:
            raise RuntimeError("DEEP_ASR_REJECTED: "+json.dumps(qa,ensure_ascii=False)[:480])
    return dict(meta,source_audio_sha256=digest(mp3),
                context_id=record.get("context_id",""),
                licence_mode="public_provider_attribution"), {
                "id":episode["id"],"sha256":digest(mp3),"seconds":audio["duration_seconds"],
                "asr_engine":engine,"lexical_coverage":qa["lexical_coverage"],
                "passed":True}

def main():
    if os.environ.get("GITHUB_REPOSITORY")!="GUSTAVA009/moto-shorts-cloud":
        raise RuntimeError("Repository mismatch")
    records=json.loads(INBOX.read_text(encoding="utf8"))
    if records.get("version")!=1 or records.get("voice_id")!="deep":
        raise ValueError("Invalid inbox")
    items=records.get("records")
    if not isinstance(items,list) or not 1<=len(items)<=MAX_RECORDS:
        raise ValueError("Invalid inbox record count")
    if len({x["episode_id"] for x in items})!=len(items):
        raise ValueError("Duplicate episode inbox keys")
    entry=github("GET","contents/"+CATALOG+"?ref=main")
    catalog=json.loads(base64.b64decode(entry["content"]))
    episodes={e["id"]:e for e in catalog["episodes"]}
    completed=[]
    with tempfile.TemporaryDirectory() as folder:
        # Verify *all* first, so one bad voice cannot partly update the catalog.
        changes=[]
        for item in items:
            ep=episodes.get(item["episode_id"])
            if ep is None:
                raise ValueError("Unknown queued episode")
            if ep.get("deep_audio"):
                if not ready(ep):
                    raise ValueError("Existing unready Deep: do not overwrite")
                print("DEEP_ALREADY_PINNED",ep["id"],flush=True)
                continue
            asset, proof=assess(item,ep,folder)
            fresh=dict(ep,narration=item["narration"],
                       title=item.get("title") or ep["title"],
                       voice_profile=PROFILE_ID,deep_audio=asset)
            validate_episode(fresh)
            changes.append((ep["id"],fresh,proof))
        if not changes:
            print("DEEP_INBOX_NO_NEW_AUDIO")
            return 0
        for key,new,proof in changes:
            episodes[key].update(new)
            completed.append(proof)
        validate_catalog(catalog)
        content=(json.dumps(catalog,ensure_ascii=False,indent=2)+"\n").encode("utf8")
        github("PUT","contents/"+CATALOG,{
            "message":"Approve genuine Deep voice assets after independent Russian ASR: "+
                      ", ".join(x["id"] for x in completed),
            "branch":"main","sha":entry["sha"],
            "content":base64.b64encode(content).decode("ascii")})
    for obj in completed:
        print("APPROVED_VERIFIED_DEEP_EPISODE",json.dumps(obj,ensure_ascii=False),flush=True)
    if os.getenv("GITHUB_EVENT_NAME")=="workflow_dispatch":
        github("POST","actions/workflows/daily-preview.yml/dispatches",{"ref":"main"})
        print("DEEP_PREVIEW_DISPATCHED",flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
