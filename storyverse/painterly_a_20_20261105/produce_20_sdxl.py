"""Resume-safe local production of all 20 original Shorts with locally generated painterly SDXL scenes.
No auto YouTube publish. Output real verified 120-second MP4s for user review.
"""
import sys,time,json,traceback,subprocess
from pathlib import Path
ROOT=Path(r"C:\Users\alex-\GUSTAVA-AI-HUB\productions\PAINTERLY_A_NEXT_120_20261105")
sys.path.insert(0,str(ROOT))
from generate_sdxl_storyboards import create
from assemble_painterly_sdxl import render
STORIES=json.loads((ROOT/"all_20_stories.json").read_text(encoding="utf8"))["items"]
STATUS=ROOT/"batch_production_status.json"
def valid_art(st,i):
 p=ROOT/"episodes"/st["slug"]/"sdxl_art_manifest.json"
 if not p.exists():return False
 try:
  a=json.loads(p.read_text(encoding="utf8"))
  f=Path(a[str(i+1)]["file"])
  return f.exists() and f.stat().st_size>200000
 except:return False
def stat():
 ret={"total_stories":20,"storyboards_ready":0,"scenes_ready":0,"complete_videos":0,
      "items":[],"last_check":time.strftime("%Y-%m-%d %H:%M:%S")}
 for st in STORIES:
  slug=st["slug"];p=ROOT/"episodes"/slug
  n=sum(valid_art(st,i) for i in range(6))
  video=p/(slug+"_PAINTERLY_A_DEEP_120s.mp4")
  video_ok=video.exists() and video.stat().st_size>8_000_000
  ret["items"].append({"slug":slug,"images":n,"video":str(video) if video_ok else None,"video_verified":(p/"FINAL_VIDEO_QA.json").exists()})
  ret["scenes_ready"]+=n
  ret["storyboards_ready"]+=(n==6)
  ret["complete_videos"]+=video_ok
 STATUS.write_text(json.dumps(ret,ensure_ascii=False,indent=2),encoding="utf8")
 return ret
def log(*a):print(*a,flush=True)
def main():
 allstories=len(STORIES)
 log("BATCH_START",allstories,"resume_safe")
 stat()
 errors=[]
 for idx,st in enumerate(STORIES):
  slug=st["slug"]
  for shot in range(6):
   if valid_art(st,shot):continue
   try:
    log("STORY_ART_START",idx+1,"/20",slug,"shot",shot+1)
    x=create(st,shot,timeout=270)
    p=ROOT/"episodes"/slug/"sdxl_art_manifest.json"
    p.parent.mkdir(parents=True,exist_ok=True)
    prev=json.loads(p.read_text(encoding="utf8")) if p.exists() else {}
    prev[str(shot+1)]=x
    p.write_text(json.dumps(prev,ensure_ascii=False,indent=2),encoding="utf8")
    log("STORY_ART_READY",slug,shot+1)
    stat()
   except Exception as e:
    msg=f"{slug} scene {shot+1}: {e}"
    errors.append(msg);log("BATCH_ART_FAILED",msg)
    try:
     time.sleep(6)
     x=create(st,shot,timeout=270)
     p=ROOT/"episodes"/slug/"sdxl_art_manifest.json"
     old=json.loads(p.read_text(encoding="utf8")) if p.exists() else {}
     old[str(shot+1)]=x
     p.write_text(json.dumps(old,ensure_ascii=False,indent=2),encoding="utf8")
     stat()
     log("RETRIED_SCENE_READY",slug,shot+1)
    except Exception as e2:
     errors.append(f"{slug} scene {shot+1} retry failed: {e2}")
     log("SKIPPING_BROKEN_SHOT",slug,shot+1,e2)
  if sum(valid_art(st,i) for i in range(6))!=6:
   log("SKIP_VIDEO_MISSING_SHOTS",slug)
   stat()
   continue
  out=ROOT/"episodes"/slug/(slug+"_PAINTERLY_A_DEEP_120s.mp4")
  if out.exists() and out.stat().st_size>8_000_000 and (out.parent/"FINAL_VIDEO_QA.json").exists():
   log("EPISODE_ALREADY_RENDERED",slug)
  else:
   try:
    log("VIDEO_ASSEMBLY_START",slug)
    render(st)
    log("VIDEO_COMPLETE",slug)
   except Exception as e:
    err=f"VIDEO {slug}: {e}"
    errors.append(err);log("VIDEO_ERROR",err,traceback.format_exc()[-700:])
  stat()
  log("BATCH_PROGRESS",json.dumps({k:stat()[k] for k in ("scenes_ready","storyboards_ready","complete_videos")}))
 (ROOT/"batch_production_errors.json").write_text(json.dumps(errors,ensure_ascii=False,indent=2),encoding="utf8")
 ret=stat()
 log("BATCH_FINISH",json.dumps({k:ret[k] for k in ("scenes_ready","storyboards_ready","complete_videos")}),"errors",len(errors))
if __name__=="__main__":main()
