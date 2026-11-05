import subprocess,json,hashlib,os,sys
from pathlib import Path
BASE=Path(r"C:\Users\alex-\GUSTAVA-AI-HUB\productions\BUS_00_REBUILD_CONTROLLED")
P=BASE/"FORMAT_B_HYBRID_V3"
frames=P/"frames"
out=P/"AVTOBUS_HYBRID_V4_SAFE_CAMERA_12S.mp4"
assert len(list(frames.glob("frame_*.png")))==288,"Render incomplete"
srt=str(BASE/"proof_subtitles_ru.srt").replace("\\","/").replace(":","\\:")
vf=("scale=720:1280:flags=lanczos,"
    f"subtitles='{srt}':force_style='Fontname=Arial,Fontsize=12,Outline=2,Shadow=0,MarginV=30,Alignment=2'")
# Action timestamps are calculated directly from the 24-fps Blender scene:
# Frame 164: door starts sliding, frame 199: door fully open.
# Frame 193: the actor starts walking toward the bus as doors finish opening.
sound=(
"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume=1.05,"
"apad=pad_dur=1,atrim=0:12[voice];"
"[2:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:4.3,asetpts=PTS-STARTPTS,"
"afade=t=in:st=0:d=0.25,afade=t=out:st=3.6:d=0.7,volume=0.14,"
"adelay=1510|1510,apad=pad_dur=12,atrim=0:12[engine];"
"[3:a]aresample=48000,aformat=channel_layouts=stereo,atrim=start=0.35:duration=1.459,asetpts=PTS-STARTPTS,"
"afade=t=in:st=0:d=0.07,afade=t=out:st=1.26:d=0.2,volume=0.20,"
"adelay=6833|6833,apad=pad_dur=12,atrim=0:12[door];"
"[4:a]aresample=48000,aformat=channel_layouts=stereo,atrim=start=4.25:duration=3.2,asetpts=PTS-STARTPTS,"
"afade=t=in:st=0:d=0.12,afade=t=out:st=2.75:d=0.45,volume=0.12,"
"adelay=8042|8042,apad=pad_dur=12,atrim=0:12[steps];"
"[5:a]aresample=48000,aformat=channel_layouts=stereo,atrim=start=14:duration=12,asetpts=PTS-STARTPTS,"
"afade=t=in:st=0:d=0.4,afade=t=out:st=11.15:d=0.85,volume=0.026[wind];"
"[voice][engine][door][steps][wind]amix=inputs=5:duration=first:dropout_transition=0:normalize=0,"
"alimiter=limit=.93,atrim=0:12[mix]"
)
assets=BASE/"cc0_sound_library"
cmd=["ffmpeg","-y","-nostdin","-hide_banner","-loglevel","error",
 "-framerate","24","-start_number","1","-i",str(frames/"frame_%04d.png"),
 "-i",str(BASE/"PROOF_DEEP_12SEC.mp3"),"-i",str(assets/"bus_engine.wav"),
 "-i",str(assets/"bus_door.wav"),"-i",str(assets/"snow_steps.wav"),
 "-i",str(assets/"winter_wind.wav"),
 "-filter_complex",sound,
 "-map","0:v:0","-map","[mix]","-vf",vf,"-c:v","libx264","-preset","fast","-crf","19",
 "-pix_fmt","yuv420p","-r","24","-c:a","aac","-b:a","192k","-ac","2","-ar","48000",
 "-t","12","-movflags","+faststart",str(out)]
print("ENCODING_V3",flush=True)
subprocess.run(cmd,check=True,timeout=210)
probe=subprocess.run(["ffprobe","-v","error","-show_entries",
"format=duration,size:stream=codec_type,codec_name,width,height,avg_frame_rate,channels",
"-of","json",str(out)],check=True,capture_output=True,text=True)
meta=json.loads(probe.stdout);streams=meta["streams"]
v=next(x for x in streams if x["codec_type"]=="video");a=next(x for x in streams if x["codec_type"]=="audio")
assert (v["width"],v["height"])==(720,1280)
assert v["avg_frame_rate"]=="24/1" and a["channels"]==2
assert abs(float(meta["format"]["duration"])-12)<.09
subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-i",str(out),"-f","null","NUL"],check=True,timeout=120)
sha=hashlib.sha256(out.read_bytes()).hexdigest()
report={
 "status":"technical_pass_pending_final_visual_approval",
 "source":"same persistent Blender scene, regenerated with sliding bus doors and safe camera",
 "fixed":["hinged door obstruction","entrance side pillar","foreground camera push-through","episode/day badge"],
 "duration":12.0,"fps":24,"resolution":"720x1280",
 "voice":"GUSTAVA DEEP (original version)",
 "sound_events":{"engine_start":1.510,"door_starts_moving":164/24,
  "door_sound_start":6.833,"door_fully_open":199/24,"walk_sound_start":193/24},
 "visual_source":"FORMAT_B_V4_SAFE_CAMERA.blend",
 "sha256":sha,"size":out.stat().st_size,
 "note":"Technical integrity and geometry tests are not a guarantee of artistic quality."
}
(P/"FINAL_V4_QA.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
print("DONE_V3",out,report["size"],sha,flush=True)
