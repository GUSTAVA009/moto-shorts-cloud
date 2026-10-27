#!/usr/bin/env python3
"""Produce an original motorcycle safety documentary preview; never publish automatically."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import wave

ROOT=Path(__file__).resolve().parent.parent
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"cloud-shorts"))
from tts_voice import render as voice_render
from soundtrack import generate as music_render
from editorial_guard import PUBLISHED_SOURCE_IDS
FONT=Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
MANIFEST=HERE/"01-rain-production.json"

def command(args,timeout=600):
    p=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError("Video pipeline failure: "+" ".join(map(str,args[:5]))+"\n"+p.stderr[-2000:])
    return p.stdout

def probe(path):
    return json.loads(command(["ffprobe","-v","error","-show_entries","format=duration:stream=codec_type,width,height","-of","json",path],60))

def validate(cfg):
    if cfg.get("schema_version")!=1 or not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,46}",str(cfg.get("id",""))):
        raise ValueError("Invalid documentary schema")
    scenes=cfg.get("segments",[])
    sources=cfg.get("sources",[])
    if len(scenes)<30 or len(sources)<12:
        raise ValueError("Documentary needs substantial new story and footage")
    ids=set()
    keys=set()
    for s in sources:
        k=s["key"]
        ident=str(s["id"])
        page=urllib.parse.urlparse(s["source_page"])
        url=urllib.parse.urlparse(s["url"])
        if k in keys or ident in ids or not re.fullmatch(r"\d{5,10}",ident):
            raise ValueError("Source ID duplicated/invalid")
        if page.scheme!="https" or page.hostname!="www.pexels.com" or not page.path.rstrip("/").endswith("-"+ident):
            raise ValueError("Missing source provenance")
        if url.scheme!="https" or url.hostname!="www.pexels.com" or url.path!="/download/video/"+ident+"/":
            raise ValueError("Only approved Pexels downloads allowed")
        if s["license"]!="Pexels License" or not s["author"]:
            raise ValueError("Source license/author missing")
        ids.add(ident);keys.add(k)
    short_catalog=json.loads((ROOT/"cloud-shorts"/"episodes.json").read_text(encoding="utf8"))
    short_ids={re.search(r"-(\d+)/?$",s["source_page"]).group(1)
               for ep in short_catalog["episodes"] for s in ep["footage"]}
    short_ids.update(PUBLISHED_SOURCE_IDS)
    if ids.intersection(short_ids):
        raise ValueError("Source previously used in Shorts catalog")
    chars=0
    for seg in scenes:
        narration=str(seg.get("narration",""))
        if any(word in narration.casefold() for word in ("хапыч", "эндуро")):
            raise ValueError("Narration contains banned channel phrase")
        if not 100<=len(narration)<=350:
            raise ValueError("Narration too short or exceeds approved TTS length")
        chars+=len(narration)
        if seg["chapter"] not in cfg["chapters"]:
            raise ValueError("Invalid chapter")
        if not seg["graphic"] and seg["visual"] not in keys:
            raise ValueError("Unknown source in segment")
        if not 5<=len(seg["caption"])<=55:
            raise ValueError("On-screen caption invalid")
    if chars<6500 or "http" in cfg["description"].lower():
        raise ValueError("Insufficient documentary commentary or unapproved public links")
    return {"new_clips":len(sources),"scenes":len(scenes),"words_characters":chars,"own_infographic_scenes":sum(x["graphic"] for x in scenes)}

def safe_download(url,target):
    if target.exists() and target.stat().st_size>300000:
        return
    target.parent.mkdir(parents=True,exist_ok=True)
    partial=target.with_suffix(".partial")
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 MotoDocumentary/1.0"}),timeout=150) as inp,partial.open("wb") as out:
            redirect=urllib.parse.urlparse(inp.geturl())
            if redirect.scheme!="https" or redirect.hostname not in {"www.pexels.com","videos.pexels.com"}:
                raise ValueError("Unexpected stock-video redirect")
            if "text/html" in (inp.headers.get("Content-Type") or "").lower():
                raise ValueError("Stock URL returned HTML")
            while True:
                chunk=inp.read(1024*1024)
                if not chunk:break
                out.write(chunk)
                if out.tell()>180000000:
                    raise ValueError("Video source exceeds 180MB safety bound")
        if partial.stat().st_size<300000:
            raise ValueError("Empty stock clip")
        partial.replace(target)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    if not any(x["codec_type"]=="video" for x in probe(target)["streams"]):
        raise ValueError("Downloaded source has no valid video stream")

def card(path,chapter,caption,index):
    from PIL import Image,ImageDraw,ImageFont
    font=lambda size:ImageFont.truetype(str(FONT),size)
    im=Image.new("RGB",(1280,720),(16,20,24))
    d=ImageDraw.Draw(im)
    for y in range(720):
        d.line(((0,y),(1280,y)),fill=(17+y//120,20+y//180,24+y//180))
    d.rectangle((0,0,16,720),fill=(255,122,21))
    d.rectangle((68,74,1198,82),fill=(255,122,21))
    d.text((70,100),"GUSTAVA ENDURO  /  РАЗБОР МОТОТЕХНИКИ",font=font(26),fill="white")
    d.text((70,220),chapter,font=font(48),fill="white")
    d.text((70,350),caption.replace("/","•"),font=font(31),fill=(255,169,68))
    for n in range(5):
        x=78+n*220
        d.ellipse((x,483,x+85,569),outline=(255,122,21) if n<=index%5 else (95,102,110),width=6)
        d.text((x+29,505),str(n+1),font=font(30),fill="white")
    d.text((70,642),"РУКОВОДСТВО К КОНКРЕТНОЙ МОДЕЛИ ВАЖНЕЕ ОБЩИХ СОВЕТОВ",font=font(21),fill=(184,185,190))
    im.save(path)

def encode(i,seg,source,voice,music,work,label,seconds,total):
    t=work/f"heading_{i:02}.txt";t.write_text(label,encoding="utf8")
    c=work/f"caption_{i:02}.txt";c.write_text(seg["caption"],encoding="utf8")
    first=["-loop","1","-i",source] if seg["graphic"] else ["-stream_loop","-1","-i",source]
    video=f"[0:v]fps=24,scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,format=yuv420p,drawbox=x=0:y=0:w=1280:h=114:color=black@0.65:t=fill,drawbox=x=0:y=600:w=1280:h=120:color=black@0.65:t=fill,drawtext=fontfile={FONT}:textfile={t}:fontcolor=white:fontsize=36:x=50:y=28:borderw=2:bordercolor=black,drawtext=fontfile={FONT}:textfile={c}:fontcolor=white:fontsize=31:x=(w-text_w)/2:y=632:borderw=2:bordercolor=black,drawbox=x=48:y=692:w=1184:h=5:color=white@0.22:t=fill,drawbox=x=48:y=692:w={int(1184*(i+1)/total)}:h=5:color=0xff780f:t=fill[v]"
    audio=f"[1:a]aresample=48000,volume=1.20[voc];[2:a]aresample=48000,volume=0.095[bed];[voc][bed]amix=inputs=2:duration=longest:dropout_transition=0,apad,atrim=duration={seconds:.3f},afade=t=out:st={seconds-0.5:.3f}:d=0.5[a]"
    out=work/f"part_{i:02}.mp4"
    command(["ffmpeg","-y","-hide_banner","-loglevel","error","-threads","2",*first,"-i",voice,"-stream_loop","-1","-i",music,"-filter_complex",video+";"+audio,"-map","[v]","-map","[a]","-t",f"{seconds:.3f}","-r","24","-c:v","libx264","-preset","veryfast","-crf","25","-pix_fmt","yuv420p","-c:a","aac","-ar","48000","-ac","2","-b:a","128k",out])
    if out.stat().st_size<30000:
        raise ValueError("Empty chapter segment")
    print("DOC_SCENE",i+1,"/",total,"duration",round(seconds,2),flush=True)
    return out

def render(cfg,out):
    info=validate(cfg)
    out.mkdir(parents=True,exist_ok=True)
    work=out/"_working";work.mkdir(exist_ok=True)
    source_by_key={x["key"]:x for x in cfg["sources"]}
    for key in sorted({s["visual"] for s in cfg["segments"] if not s["graphic"]}):
        safe_download(source_by_key[key]["url"],work/(key+".mp4"))
    soundtrack=work/"music_original.wav"
    music_render(soundtrack,seconds=160.0,bpm=101,style="desert-cinematic",seed=69412)
    files=[];duration=0
    for i,seg in enumerate(cfg["segments"]):
        wav=work/f"speech_{i:02}.wav"
        voice_render(seg["narration"],wav,work/"model")
        with wave.open(str(wav),"rb") as w:
            seconds=w.getnframes()/w.getframerate()+1.2
        if seg["graphic"]:
            clip=work/f"diagram_{i:02}.png"
            card(clip,cfg["chapters"][seg["chapter"]][0],seg["caption"],cfg["chapters"][seg["chapter"]][1])
        else:
            clip=work/(seg["visual"]+".mp4")
        files.append(encode(i,seg,clip,wav,soundtrack,work,cfg["chapters"][seg["chapter"]][0],seconds,len(cfg["segments"])))
        duration+=seconds
    manifest=work/"concat.ffcat"
    manifest.write_text("ffconcat version 1.0\n"+"".join("file '"+x.name+"'\n" for x in files),encoding="utf8")
    destination=out/(cfg["id"]+".mp4")
    command(["ffmpeg","-y","-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",manifest,"-c","copy","-movflags","+faststart",destination])
    result=probe(destination);sec=float(result["format"]["duration"])
    if sec<220 or not {"audio","video"}<=set(x["codec_type"] for x in result["streams"]):
        raise ValueError("Long video QA failed")
    card(out/"thumbnail.png","5 ПРОВЕРОК ПЕРЕД ДОЖДЁМ","ШИНЫ • ТОРМОЗА • ОБЗОР",2)
    (out/"publication.json").write_text(json.dumps({k:cfg[k] for k in ("id","title","description")},ensure_ascii=False,indent=2),encoding="utf8")
    (out/"source_rights.json").write_text(json.dumps({"sources":cfg["sources"],"facts":cfg["fact_sources"],"disclaimer":cfg["production_disclaimer"]},ensure_ascii=False,indent=2),encoding="utf8")
    (out/"qa.json").write_text(json.dumps({**info,"seconds":sec,"bytes":destination.stat().st_size,"human_approval_required":True,"public_upload_permitted":False},ensure_ascii=False,indent=2),encoding="utf8")
    print("DOCUMENTARY_PREVIEW_READY",round(sec,1),"seconds",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--check-only",action="store_true")
    p.add_argument("--out",type=Path,default=HERE/"dist"/"rain-checklist-long-01")
    args=p.parse_args()
    cfg=json.loads(MANIFEST.read_text(encoding="utf8"))
    print("DOCUMENTARY_EDITORIAL_CHECK",validate(cfg),flush=True)
    if not args.check_only:render(cfg,args.out)

if __name__=="__main__":
    main()
