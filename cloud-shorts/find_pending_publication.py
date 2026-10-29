#!/usr/bin/env python3
"""Find the oldest new, unsent, ASR-approved Shorts artifact for retry-safe delivery.

Research-only stories, previous publishes, and legacy renders without ASR
evidence are never released. No media is downloaded or posted by this selector.
"""
import argparse
import json
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request
import base64

import preview_queue as ledger
from channel_focus import is_motorcycle_episode


def gh(path):
    token=os.environ.get("GITHUB_TOKEN","")
    repo=os.environ.get("GITHUB_REPOSITORY","")
    if not token or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",repo):
        raise RuntimeError("GitHub authentication not present")
    url="https://api.github.com/repos/"+repo+"/"+path
    req=urllib.request.Request(url,headers={
        "Authorization":"Bearer "+token,
        "Accept":"application/vnd.github+json",
        "User-Agent":"gustava-queued-publisher"
    })
    with urllib.request.urlopen(req,timeout=35) as res:
        return json.loads(res.read(5_000_000))


def select(catalog, receipt_entries, published, artifacts):
    # Retired Piper/Silero voices must NEVER re-enter the public backlog.
    # Only newly reviewed native-Russian male Kokoro originals are eligible.
    allowed={ep["id"] for ep in catalog["episodes"]
             if ep.get("auto_publish") is True
             and ep.get("voice_engine") == "kokoro_ru_dima"
             and is_motorcycle_episode(ep)}
    available={x["name"] for x in artifacts if not x.get("expired")}
    choices=[]
    for obj in receipt_entries:
        slug=obj.get("id")
        if slug not in allowed or obj.get("state")!="preview_ready":
            continue
        if (obj.get("voice_qa_passed") is not True
                or obj.get("mixed_audio_qa_passed") is not True
                or slug in published):
            continue
        run=str(obj.get("run_id",""))
        if not run.isdigit():
            continue
        name=f"daily-preview-{slug}-{run}"
        if name in available:
            choices.append((int(run),slug,name))
    return min(choices) if choices else None


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    tree=gh("git/trees/render-ledger?recursive=1")
    paths=[x["path"] for x in tree.get("tree",[]) if x["path"].startswith("render-receipts/") and x["path"].endswith(".json")]
    published={Path(x["path"]).stem for x in tree.get("tree",[]) if x["path"].startswith("publication-receipts/") and x["path"].endswith(".json")}
    receipts=[]
    for path in paths:
        entry=ledger.api(path)
        if entry and entry.get("content"):
            receipts.append(json.loads(base64.b64decode(entry["content"])))
    catalog=json.loads(Path(__file__).with_name("episodes.json").read_text(encoding="utf8"))
    artifacts=gh("actions/artifacts?per_page=100").get("artifacts",[])
    result=select(catalog,receipts,published,artifacts)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if result:
        run,slug,name=result
        args.output.write_text(f"has_job=true\nepisode={slug}\nrender_id={run}\nartifact_name={name}\n",encoding="utf8")
        print("BACKLOG_ASR_PASSED",slug,"run",run)
    else:
        args.output.write_text("has_job=false\n",encoding="utf8")
        print("NO_PUBLISHABLE_NEW_MP4: closed, duplicates prevented")


if __name__=="__main__":
    main()
