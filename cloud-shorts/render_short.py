#!/usr/bin/env python3
"""Licensed Pexels footage + original Russian commentary -> one Shorts MP4.
No personal-device files, subscriptions, publishing tokens, or paid APIs.
"""
import json
import os
import subprocess
import urllib.request
from pathlib import Path
from soundtrack import generate as generate_soundtrack

ROOT=Path(__file__).resolve().parent
A=ROOT/"assets"
O=ROOT/"dist"
A.mkdir(exist_ok=True); O.mkdir(exist_ok=True)
FILES={
 "hill":("https://videos.pexels.com/video-files/5803637/5803637-uhd_1440_2560_25fps.mp4",A/"hill.mp4"),
 "friends":("https://videos.pexels.com/video-files/5803517/5803517-uhd_1440_2560_25fps.mp4",A/"friends.mp4"),
 "voice":("https://storage.googleapis.com/adm--audio-playback--7d--public/mcp-preview/3f6aa5a9-e12f-403e-bb72-12c5fb181adc.mp3",A/"voice.mp3")
}
SHOTS=[("hill",0.8,2.0),("friends",0.2,3.1),("friends",4.2,2.8),
       ("hill",3.4,2.5),("hill",7.0,3.3)]
CAPTIONS=[("ВЫЙДУ НА ПЯТЬ МИНУТ",0.05,2.0),
          ("ОДИН КОРОТКИЙ КРУГ",4.3,6.9),
          ("АГА... КОРОТКИЙ!",7.6,9.0),
          ("А ТЫ БЫ РИСКНУЛ?",10.8,13.65)]

def run(args,timeout=180):
 print("RUN",args[0]," ".join(map(str,args[1:]))[:180],flush=True)
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 if p.returncode:
  raise RuntimeError(p.stderr[-2500:] or "nonzero exit status")
 return p.stdout

def probe(path):
 j=json.loads(run(["ffprobe","-v","error","-show_entries",
    "format=duration:stream=codec_type,width,height","-of","json",str(path)],25))
 return float(j["format"]["duration"]),j.get("streams",[])

def fetch(url,out,min_bytes):
 if out.is_file() and out.stat().st_size>=min_bytes:
  return
 request=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
 temp=out.with_suffix(".part")
 try:
  with urllib.request.urlopen(request,timeout=110) as response,temp.open("wb") as f:
   while True:
    buf=response.read(1024*1024)
    if not buf:break
    f.write(buf)
  if temp.stat().st_size<min_bytes:raise RuntimeError("Downloaded file is too small "+str(out))
  temp.replace(out)
 except Exception:
  temp.unlink(missing_ok=True)
  raise
 print("DOWNLOADED",out.name,out.stat().st_size,flush=True)

def main():
 for k,(url,p) in FILES.items():
  fetch(url,p,100000 if k!="voice" else 8000)
 vdur,astreams=probe(FILES["voice"][1])
 assert any(s["codec_type"]=="audio" for s in astreams), "Voice file lacks audio track"
 print("VOICE_SECONDS",vdur,flush=True)
 parts=[]
 for i,(name,start,seconds) in enumerate(SHOTS):
  src=FILES[name][1]
  duration,streams=probe(src)
  assert any(s["codec_type"]=="video" for s in streams), "Source without video"
  assert duration>start+seconds-.15, "Unexpected source duration: "+name
  target=A/("cut_%02d.mp4"%i)
  run(["ffmpeg","-hide_banner","-loglevel","error","-y",
       "-ss",str(start),"-i",str(src),"-t",str(seconds),
       "-vf","fps=30,scale=720:1280:force_original_aspect_ratio=increase:flags=lanczos,crop=720:1280,setsar=1,format=yuv420p",
       "-an","-c:v","libx264","-preset","veryfast","-crf","22",
       "-pix_fmt","yuv420p","-r","30",str(target)],150)
  parts.append(target)
 listpath=A/"list.txt"
 listpath.write_text("".join("file '%s'\n"%p.name for p in parts),encoding="utf-8")
 silent=A/"assembled.mp4"
 run(["ffmpeg","-hide_banner","-loglevel","error","-y",
      "-f","concat","-safe","0","-i",str(listpath),"-an","-c","copy",str(silent)],120)
 total,_=probe(silent)
 soundtrack_path=A/"original_action_music.wav"
 music_info=generate_soundtrack(soundtrack_path,total)
 print("MUSIC_READY",music_info,flush=True)
 font="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
 assert Path(font).is_file(),"Missing Cyrillic font"
 filters=[]
 for i,(caption,lo,hi) in enumerate(CAPTIONS):
  path=A/("caption_%02d.txt"%i)
  path.write_text(caption,encoding="utf-8")
  filters.append("drawbox=x=30:y=135:w=660:h=86:color=black@0.38:t=fill:enable='between(t,%s,%s)'"%(lo,hi))
  filters.append("drawtext=fontfile=%s:textfile=%s:fontsize=37:fontcolor=white:shadowcolor=black@0.95:shadowx=2:shadowy=2:x=(w-text_w)/2:y=154:enable='between(t,%s,%s)'"%(font,path,lo,hi))
 filters.append("fade=t=out:st=%.2f:d=0.35"%(total-.35))
 output=O/"first_motorcycle_short.mp4"
 run(["ffmpeg","-hide_banner","-loglevel","error","-y",
      "-i",str(silent),"-i",str(FILES["voice"][1]),"-i",str(soundtrack_path),
      "-filter_complex",(
          "[0:v]"+",".join(filters)+"[v];"
          "[1:a]aresample=48000,highpass=f=90,lowpass=f=9200,volume=1.12,"
          "adelay=250|250,apad,atrim=duration=%.3f,asetpts=PTS-STARTPTS,asplit=2[voice_duck][voice_mix];"%total+
          "[2:a]aresample=48000,volume=0.48,afade=t=in:st=0:d=0.16,"
          "afade=t=out:st=%.3f:d=0.48,atrim=duration=%.3f,asetpts=PTS-STARTPTS[bed];"
          %(max(0,total-0.48),total)+
          "[bed][voice_duck]sidechaincompress=threshold=0.025:ratio=6:attack=12:release=230[ducked];"
          "[ducked][voice_mix]amix=inputs=2:duration=first:normalize=0,"
          "alimiter=limit=0.93[a]"),
      "-map","[v]","-map","[a]","-c:v","libx264","-preset","medium","-crf","21",
      "-r","30","-pix_fmt","yuv420p","-c:a","aac","-b:a","160k","-ar","48000",
      "-movflags","+faststart","-t",str(total),str(output)],230)
 duration,streams=probe(output)
 assert 12<=duration<=17 and output.stat().st_size>500000,"Unexpected final MP4"
 assert any(s["codec_type"]=="video" and s.get("width")==720 and s.get("height")==1280 for s in streams)
 assert any(s["codec_type"]=="audio" for s in streams)
 run(["ffmpeg","-hide_banner","-loglevel","error","-y",
      "-ss","0.8","-i",str(output),"-frames:v","1",str(O/"thumbnail.jpg")],30)
 summary={
  "title":"Выехал на 5 минут… А тут такое! 😳 #shorts",
  "description":"Когда обещал вернуться через пять минут, но друзья позвали на один «короткий круг»! 😅 А ты бы рискнул пройти этот подъём? Пиши в комментариях!\n\n#мото #мотокросс #shorts",
  "duration_seconds":round(duration,2),"status":"READY_FOR_REVIEW",
  "youtube_published":False,
  "background_music":{"type":"original procedural instrumental","generator":"cloud-shorts/soundtrack.py","ducked_under_voice":True},
  "source_pages":["https://www.pexels.com/video/person-riding-a-motocross-5803637/","https://www.pexels.com/video/people-riding-dirt-bikes-5803517/"]
 }
 (O/"publication.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
 print("VIDEO_READY",str(output),"BYTES",output.stat().st_size,"DURATION",round(duration,2),flush=True)

if __name__=="__main__":
 main()
