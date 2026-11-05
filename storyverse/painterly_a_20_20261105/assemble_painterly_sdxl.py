"""Compose original artist-checked 2D SDXL panels into a real 120s YouTube Short.
Video is Ken Burns illustrated cinema (user allows animated slides), not full body rig.
Preserves original narrator GUSTAVA DEEP with separate audio layers.
"""
from pathlib import Path
import os,sys,json,subprocess,math,hashlib,time,random
from PIL import Image,ImageDraw
import numpy as np,cv2
ROOT=Path(r"C:\Users\alex-\GUSTAVA-AI-HUB\productions\PAINTERLY_A_NEXT_120_20261105")
sys.path.insert(0,str(ROOT))
from render_painterly_A import build_audio
STORIES=json.loads((ROOT/"all_20_stories.json").read_text(encoding="utf8"))["items"]
FPS=30
def run(cmd,timeout=290):
    print("RUNNING",cmd[0],(" ".join(cmd[-6:]))[:260],flush=True)
    r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)
    if r.returncode:raise RuntimeError("FFMPEG_FAILED "+r.stderr[-1700:])
def make_snow(root):
    p=root/"snow_overlay_local.mp4"
    if p.exists() and p.stat().st_size>80000:return p
    w,h=360,640;fps=30;frames=180
    wr=cv2.VideoWriter(str(p),cv2.VideoWriter_fourcc(*"mp4v"),fps,(w,h))
    if not wr.isOpened():raise RuntimeError("snow overlay writer unavailable")
    rng=random.Random(281019)
    flakes=[(rng.randint(0,w),rng.randint(0,h),rng.choice([1,2]),rng.choice([.5,1,2]),rng.randint(165,255)) for _ in range(105)]
    for n in range(frames):
        f=np.zeros((h,w,3),dtype=np.uint8)
        for x0,y0,k,r,bri in flakes:
            yy=int((y0+n*h*k/frames)%h)
            xx=int((x0+n*w*.25/frames)%w)
            cv2.circle(f,(xx,yy),1 if r<1.5 else 2,(bri,bri,bri),-1,cv2.LINE_AA)
        wr.write(f)
    wr.release()
    return p
def video_count(image_root):
    p=image_root/"sdxl_art_manifest.json"
    if not p.exists():return 0
    manifest=json.loads(p.read_text(encoding="utf8"))
    return len([i for i in range(1,7) if str(i) in manifest and Path(manifest[str(i)]["file"]).exists()])
def render(story):
    slug=story["slug"];root=ROOT/"episodes"/slug
    artifact=root/"sdxl_art_manifest.json"
    if video_count(root)!=6:raise RuntimeError("NOT_SIX_SDXL_SCENES "+slug)
    art=json.loads(artifact.read_text(encoding="utf8"))
    voice,parts,bounds=build_audio(story)
    if sum(parts)<=110:raise RuntimeError("SHORT_SCRIPT_AUDIO")
    parts[-1]+=120-sum(parts)
    counts=[int(round(n*FPS)) for n in parts]
    counts[-1]+=3600-sum(counts)
    assert sum(counts)==3600,counts
    tmp=root/"edit";tmp.mkdir(exist_ok=True)
    segments=[]
    for i in range(6):
        img=Path(art[str(i+1)]["file"])
        if not img.exists():raise RuntimeError("MISSING_IMAGE "+str(img))
        sz=Image.open(img).size
        if min(sz)<640:raise RuntimeError("LOW_RES_IMAGE "+str(img)+str(sz))
        out=tmp/f"scene_{i+1:02d}.mp4"
        fnum=counts[i]
        # Bounded deterministic camera motion. Every scene has its own original painting.
        if i%2==0:zz=f"1.025+0.06*on/{fnum}"
        else:zz=f"1.10-0.06*on/{fnum}"
        zoom=f"zoompan=z='{zz}':x='max(0,min(iw-iw/zoom,(iw-iw/zoom)/2+8*sin(on/97)))':y='max(0,min(ih-ih/zoom,(ih-ih/zoom)/2+11*cos(on/121)))':d=1:s=720x1280:fps=30"
        vf="scale=960:1706:force_original_aspect_ratio=increase:flags=lanczos,crop=960:1706,"+zoom+",format=yuv420p"
        cmd=["ffmpeg","-y","-nostdin","-hide_banner","-loglevel","error",
             "-loop","1","-framerate","30","-i",str(img),
             "-vf",vf,"-frames:v",str(fnum),
             "-c:v","h264_nvenc","-preset","p4","-rc","vbr","-cq","21","-b:v","0",
             "-pix_fmt","yuv420p","-r","30","-movflags","+faststart",str(out)]
        print("START_SCENE",slug,i+1,"frames",fnum,"source",sz,flush=True)
        run(cmd,timeout=260)
        segments.append(out)
        print("FINISHED_SCENE",i+1,"size",out.stat().st_size,flush=True)
    concat=tmp/"concatenate.txt"
    concat.write_text("".join("file '"+str(x).replace("\\","/")+"'\n" for x in segments),encoding="utf8")
    joined=tmp/"picture_120sec_no_audio.mp4"
    run(["ffmpeg","-y","-nostdin","-hide_banner","-loglevel","error","-f","concat",
         "-safe","0","-i",str(concat),"-c","copy",str(joined)])
    snow=make_snow(ROOT)
    out=root/(slug+"_PAINTERLY_A_DEEP_120s.mp4")
    # Snow from fixed original particle positions; deterministic and 100% local.
    fc="[1:v]scale=720:1280,colorkey=black:0.08:0.17,colorchannelmixer=aa=0.30[flakes];[0:v][flakes]overlay=0:0:shortest=1:format=auto,scale=1080:1920:flags=lanczos,format=yuv420p[v]"
    final=["ffmpeg","-y","-nostdin","-hide_banner","-loglevel","error",
      "-i",str(joined),"-stream_loop","-1","-i",str(snow),"-i",str(voice),
      "-filter_complex",fc,"-map","[v]","-map","2:a:0",
      "-c:v","h264_nvenc","-preset","p4","-rc","vbr","-cq","21","-b:v","0",
      "-r","30","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-ar","48000","-ac","2",
      "-t","120","-movflags","+faststart",str(out)]
    print("FINAL_MIX_RUNNING",slug,flush=True)
    run(final,timeout=400)
    probe=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration,size:stream=codec_name,codec_type,avg_frame_rate,width,height,channels",
     "-of","json",str(out)],capture_output=True,text=True,check=True,timeout=30)
    info=json.loads(probe.stdout)
    streams=info["streams"]
    v=next(x for x in streams if x.get("codec_type")=="video")
    a=next(x for x in streams if x.get("codec_type")=="audio")
    assert (v["width"],v["height"])==(1080,1920),(v,info)
    assert v["avg_frame_rate"]=="30/1"
    assert a["channels"]==2
    assert abs(float(info["format"]["duration"])-120)<.3
    run(["ffmpeg","-v","error","-i",str(out),"-f","null","NUL"],timeout=250)
    sha=hashlib.sha256(out.read_bytes()).hexdigest()
    report={
      "episode":slug,"voice":"GUSTAVA DEEP","voice_parts":6,"real_MP4":True,
      "image_source":"ByteDance SDXL-Lightning (OpenRAIL++ license) locally generated images",
      "animation":"deterministic Ken Burns motion on 6 unique painted images + generated moving snow",
      "fps":30,"duration_seconds":round(float(info["format"]["duration"]),3),
      "resolution":"1080x1920","audio":"AAC stereo",
      "qa_codec":"pass","qa_visual":"pending human approval","publish_ready":False,
      "size":out.stat().st_size,"sha256":sha,"path":str(out),
      "scene_timings_s":parts
    }
    (root/"FINAL_VIDEO_QA.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
    print("MP4_FINISHED",json.dumps(report,ensure_ascii=False),flush=True)
    # Contact sheet taken from the ACTUAL encoded MP4.
    contact=Image.new("RGB",(240*3,427*2),(20,29,44))
    current=0
    for i,sec in enumerate([sum(parts[:k])+parts[k]/2 for k in range(6)]):
      snap=tmp/f"sample_{i:02d}.jpg"
      run(["ffmpeg","-y","-loglevel","error","-ss",str(sec),"-i",str(out),"-frames:v","1",str(snap)],timeout=20)
      frame=Image.open(snap).convert("RGB").resize((240,427))
      contact.paste(frame,((i%3)*240,(i//3)*427))
    contact.save(root/"FINAL_MP4_CONTACT_6.jpg",quality=90)
    return out
if __name__=="__main__":
    slug=sys.argv[1] if len(sys.argv)>1 else STORIES[0]["slug"]
    target=next(s for s in STORIES if s["slug"]==slug)
    render(target)
