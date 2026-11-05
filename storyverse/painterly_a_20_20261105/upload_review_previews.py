"""Publish only REVIEW PREVIEWS as GitHub prerelease, never to YouTube.
Uses existing GitHub credential helper and a single reusable release.
Resume-safe: existing assets are skipped.
"""
import sys,os,json,subprocess,urllib.request,urllib.error,urllib.parse,time
from pathlib import Path
ROOT=Path(r"C:\Users\alex-\GUSTAVA-AI-HUB\productions\PAINTERLY_A_NEXT_120_20261105")
API="https://api.github.com/repos/GUSTAVA009/moto-shorts-cloud"
TAG="gustava-painterly-A-20261105-20-review"
os.environ["GIT_TERMINAL_PROMPT"]="0";os.environ["GCM_INTERACTIVE"]="never"
c=subprocess.run(["git","credential","fill"],input="protocol=https\nhost=github.com\n\n",text=True,capture_output=True,timeout=18)
fields=dict(x.split("=",1) for x in c.stdout.splitlines() if "=" in x)
TOKEN=fields.get("password")
if not TOKEN:raise RuntimeError("No GitHub authorization. Nothing uploaded.")
def request(url,method="GET",payload=None,data_type="application/vnd.github+json",timeout=50):
 headers={"Authorization":"Bearer "+TOKEN,"Accept":"application/vnd.github+json","User-Agent":"GUSTAVA-Storyverse-Preview-Delivery"}
 if payload is not None:
  headers["Content-Type"]=data_type
  if not isinstance(payload,bytes):
   payload=json.dumps(payload,ensure_ascii=False).encode("utf8")
 r=urllib.request.Request(url,data=payload,headers=headers,method=method)
 try:
  with urllib.request.urlopen(r,timeout=timeout) as f:
   out=f.read()
   return json.loads(out) if out else {}
 except urllib.error.HTTPError as e:
  detail=e.read().decode("utf8","replace")[-550:]
  raise RuntimeError(f"{method} HTTP {e.code} for {url.split('?')[0]}: {detail}")
def create_release():
 try:
  r=request(API+"/releases/tags/"+TAG)
 except RuntimeError as e:
  if "HTTP 404" not in str(e):raise
  r=request(API+"/releases","POST",{
   "tag_name":TAG,
   "target_commitish":"feature/storyverse-a-20-voice-production",
   "name":"GUSTAVA — Painterly A — 20 original Shorts — review copies",
   "body":"Черновые MP4 для художественной проверки. 2 минуты, вертикальный формат, GUSTAVA DEEP. Это НЕ публикации на YouTube. Не утверждены для автопубликации. Каждый файл имеет 6 иллюстрированных сцен с движением камеры и отдельную дорожку оригинальной русской озвучки.",
   "prerelease":True,
   "draft":False
  })
 print("GITHUB_REVIEW_RELEASE",r.get("html_url"),flush=True)
 return r
def assets(r):
 a=request(API+"/releases/"+str(r["id"])+"/assets?per_page=100")
 return {x["name"]:x for x in a}
def encode_preview(slug):
 root=ROOT/"episodes"/slug
 src=root/(slug+"_PAINTERLY_A_DEEP_120s.mp4")
 qa=root/"FINAL_VIDEO_QA.json"
 if not (src.exists() and qa.exists()):return None
 meta=json.loads(qa.read_text(encoding="utf8"))
 if meta.get("qa_codec")!="pass" or meta.get("duration_seconds",0)<119:raise RuntimeError("Unverified video file "+slug)
 compact=root/(slug+"_PREVIEW_120s.mp4")
 if not compact.exists() or compact.stat().st_size<7_000_000:
  out=subprocess.run(["ffmpeg","-nostdin","-y","-hide_banner","-loglevel","error","-i",str(src),
   "-c:v","h264_nvenc","-preset","p4","-cq","29","-b:v","0","-maxrate","3M","-bufsize","6M",
   "-c:a","copy","-movflags","+faststart",str(compact)],
   capture_output=True,text=True,timeout=150)
  if out.returncode:
   raise RuntimeError("Compression error "+slug+" "+out.stderr[-400:])
 return compact
def upload(release,path):
 title=path.name
 upload_url=release["upload_url"].split("{")[0]+"?name="+urllib.parse.quote(title,safe="")
 blob=path.read_bytes()
 headers={"Authorization":"Bearer "+TOKEN,"Accept":"application/vnd.github+json","Content-Type":"video/mp4","Content-Length":str(len(blob)),"User-Agent":"GUSTAVA-Storyverse-Preview-Delivery"}
 q=urllib.request.Request(upload_url,data=blob,headers=headers,method="POST")
 try:
  with urllib.request.urlopen(q,timeout=185) as f:r=json.loads(f.read())
 except urllib.error.HTTPError as e:
  raise RuntimeError("ASSET_HTTP_"+str(e.code)+" "+e.read().decode("utf8","replace")[:500])
 print("UPLOADED_PREVIEW",title,r.get("browser_download_url"),len(blob),flush=True)
 return r
def main():
 release=create_release();present=assets(release)
 all_stories=json.loads((ROOT/"all_20_stories.json").read_text(encoding="utf8"))["items"]
 for story in all_stories:
  slug=story["slug"];name=slug+"_PREVIEW_120s.mp4"
  if name in present:
   print("ALREADY_DELIVERED",name,flush=True);continue
  if not (ROOT/"episodes"/slug/"FINAL_VIDEO_QA.json").exists():continue
  try:
   path=encode_preview(slug)
   if path is not None:
    item=upload(release,path);present[name]=item
  except Exception as e:
   print("PREVIEW_DELIVERY_ERROR",slug,str(e),flush=True)
 print("RELEASE_PREVIEW_COUNT",len([k for k in present if k.endswith("_PREVIEW_120s.mp4")]),flush=True)
if __name__=="__main__":main()
