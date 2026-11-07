#!/usr/bin/env python3
"""Autonomously verify curated Pexels motorcycle sources at native 2K/4K.

No re-render or image upscaling. Every verified source is:
- already listed in the editorially vetted licensed Pexels pool;
- downloaded only from official HTTPS Pexels CDN, max 90MB;
- inspected with real ffprobe;
- pinned by immutable SHA256, byte count, and source pixels.
Records failures without marking a source ready. Running this does not publish.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from production_quality import available_portrait_crop
import tempfile
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parent
POOL=ROOT/"verified_pexels_pool.json"
STATE=ROOT/"native_stock_scan_state.json"
MAX_SOURCE_BYTES=90_000_000
SAFE_ID=re.compile(r"\d{4,12}\Z")


def atomic_json(path, obj):
    target=path.with_suffix(path.suffix+".tmp")
    target.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    target.replace(path)


def source_id(source):
    url=urllib.parse.urlsplit(str(source.get("url") or ""))
    m=re.fullmatch(r"/download/video/(\d+)/?",url.path)
    if (url.scheme!="https" or url.hostname!="www.pexels.com"
            or url.port not in (None,443) or url.username or url.password
            or url.query or url.fragment or not m):
        return None
    token=m.group(1)
    page=str(source.get("source_page") or "").rstrip("/")
    if not page.startswith("https://www.pexels.com/video/") or not re.search(
            r"(?:-|/)"+re.escape(token)+r"\Z",page):
        return None
    if (source.get("license")!="Pexels License"
            or not str(source.get("author") or "").strip()):
        return None
    return token


def ffprobe_video(path):
    out=subprocess.check_output([
        "ffprobe","-v","error","-select_streams","v:0",
        "-show_entries","stream=width,height:format=duration",
        "-of","json",str(path)],text=True,timeout=30)
    data=json.loads(out)
    v=data["streams"][0]
    return int(v["width"]),int(v["height"]),float(data["format"]["duration"])


def verify_one(source, cache_dir):
    sid=source_id(source)
    if not sid or not SAFE_ID.fullmatch(sid):
        return "invalid_licensed_source",None
    path=cache_dir/("pexels-"+sid+".mp4")
    if not path.exists():
        req=urllib.request.Request(source["url"],headers={
            "User-Agent":"Mozilla/5.0",
            "Accept":"video/mp4,*/*"})
        try:
            with urllib.request.urlopen(req,timeout=65) as reply:
                target=urllib.parse.urlsplit(reply.geturl())
                if (target.scheme!="https" or target.hostname!="videos.pexels.com"
                        or not target.path.startswith("/video-files/"+sid+"/")):
                    return "unexpected_cdn_or_redirect",None
                # Screen the offered CDN rendition before downloading 90MB.
                # 2160x4096 genuinely crops to 2160x3840; do not require an
                # EXACT 9:16 original, but never allow fewer real pixels.
                candidates=re.findall(
                    r"[_-](\d{3,4})_(\d{3,4})(?=[_.-])",target.path)
                crops=[available_portrait_crop(int(w),int(h))
                       for w,h in candidates]
                if not any(w>=1440 and h>=2560 for w,h in crops):
                    return "no_native_portrait_rendition",None
                declared=reply.headers.get("Content-Length")
                if declared and int(declared)>MAX_SOURCE_BYTES:
                    return "source_above_90MB_cap",None
                tmp=path.with_suffix(".download.tmp")
                count=0
                try:
                    with tmp.open("wb") as output:
                        while True:
                            block=reply.read(1<<20)
                            if not block:break
                            count+=len(block)
                            if count>MAX_SOURCE_BYTES:
                                return "source_above_90MB_cap",None
                            output.write(block)
                    tmp.replace(path)
                finally:
                    tmp.unlink(missing_ok=True)
        except urllib.error.HTTPError as error:
            if error.code==429 or 500<=error.code<=599:
                return "temporary_http_"+str(error.code),None
            return "source_http_"+str(error.code),None
        except (OSError,urllib.error.URLError,TimeoutError,ValueError) as error:
            return "temporary_"+type(error).__name__,None
    try:
        size=path.stat().st_size
        if not 1_000_000<=size<=MAX_SOURCE_BYTES:
            raise ValueError("invalid_file_size")
        w,h,duration=ffprobe_video(path)
        crop_w,crop_h=available_portrait_crop(w,h)
        if crop_w<1440 or crop_h<2560:
            raise ValueError("source_is_not_native_2k_or_4k")
        if duration<4.5:
            raise ValueError("source_too_short")
        with path.open("rb") as check:
            digest=hashlib.file_digest(check,"sha256").hexdigest()
        profile=("4k" if crop_w>=2160 and crop_h>=3840 else "2k")
        return "verified_"+profile,{
            "native_"+profile+"_sha256":digest,
            "native_"+profile+"_bytes":size,
            "native_"+profile+"_width":w,
            "native_"+profile+"_height":h,
        }
    except (OSError,ValueError,IndexError,KeyError,
            subprocess.CalledProcessError,subprocess.TimeoutExpired) as err:
        path.unlink(missing_ok=True)
        return "media_probe_failed_"+type(err).__name__,None


def harvest(max_files=2,max_checks=24,ids=(),cache=None):
    if not 1<=max_files<=15 or not 1<=max_checks<=93:
        raise ValueError("unsafe_harvester_budget")
    bank=json.loads(POOL.read_text(encoding="utf8"))
    if bank.get("version")!=1 or not isinstance(bank.get("sources"),list):
        raise RuntimeError("CURATED_PEXELS_POOL_INVALID")
    state=(json.loads(STATE.read_text(encoding="utf8"))
           if STATE.is_file() else {"version":1,"scanned":{}})
    if state.get("version")!=1 or not isinstance(state.get("scanned"),dict):
        raise RuntimeError("NATIVE_SOURCE_SCAN_STATE_INVALID")
    cache_dir=Path(cache or os.getenv("GUSTAVA_NATIVE_STOCK_CACHE")
                   or Path(tempfile.gettempdir())/"gustava-native-stock")
    cache_dir.mkdir(parents=True,exist_ok=True)
    selected=set(ids)
    entries=[s for s in bank["sources"]
             if (source_id(s) in selected if selected
                 else source_id(s) not in state["scanned"])
             and not any(str(k).startswith("native_") for k in s)]
    entries.sort(key=lambda x: (source_id(x) not in selected if selected else False,
                                source_id(x) or ""))
    complete=0
    examined=0
    for source in entries:
        if examined>=max_checks or complete>=max_files:
            break
        sid=source_id(source)
        if not sid:
            continue
        examined+=1
        status,proof=verify_one(source,cache_dir)
        if proof:
            if any(k.startswith("native_") for k in source):
                raise RuntimeError("REFUSING_TO_OVERWRITE_PINNED_NATIVE_PROOF")
            source.update(proof)
            complete+=1
            print("NATIVE_STOCK_VERIFIED",sid,status,proof,flush=True)
        else:
            print("NATIVE_STOCK_REJECTED",sid,status,flush=True)
        if not status.startswith("temporary_"):
            state["scanned"][sid]={"result":status,"date":dt.datetime.now(
                dt.timezone.utc).date().isoformat()}
        if status=="temporary_http_429":
            print("NATIVE_STOCK_RATE_LIMITED_STOP_THIS_CYCLE",flush=True)
            break
    if examined:
        atomic_json(STATE,state)
    if complete:
        atomic_json(POOL,bank)
    print("NATIVE_STOCK_HARVEST_REPORT",json.dumps({
        "checked":examined,"new_native_origins":complete,
        "prior_checked":len(state["scanned"]),
        "remaining_unpinned":sum(
            1 for s in bank["sources"]
            if source_id(s) and not any(str(k).startswith("native_") for k in s)
        ),
    }),flush=True)
    return complete


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--max-files",type=int,default=2)
    parser.add_argument("--max-checks",type=int,default=24)
    parser.add_argument("--ids",type=str,default="")
    parser.add_argument("--cache",type=str,default=None)
    args=parser.parse_args()
    ids=tuple(x for x in args.ids.split(",") if x)
    if any(not SAFE_ID.fullmatch(x) for x in ids):
        raise ValueError("Invalid source ID selection")
    harvest(args.max_files,args.max_checks,ids,args.cache)


if __name__=="__main__":
    main()
