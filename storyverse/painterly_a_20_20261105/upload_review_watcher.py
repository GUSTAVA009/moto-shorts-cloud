"""Run as part of the currently initiated local production job.
Uploads review copies to an existing PUBLIC GitHub prerelease, NEVER YouTube.
"""
import sys,time,json,subprocess,traceback
from pathlib import Path
ROOT=Path(r"C:\Users\alex-\GUSTAVA-AI-HUB\productions\PAINTERLY_A_NEXT_120_20261105")
sys.path.insert(0,str(ROOT))
import upload_review_previews as previews
done=0
for tick in range(150):
 try:
  status_file=ROOT/"batch_production_status.json"
  status=json.loads(status_file.read_text(encoding="utf8")) if status_file.exists() else {}
  n=status.get("complete_videos",0)
  if n>done:
   print("NEW_LOCAL_VIDEO_COUNT",n,flush=True)
   previews.main()
   done=n
  if n>=20:
   print("ALL_VIDEOS_UPLOADED_IF_NO_ERRORS",n,flush=True);break
  if tick%8==0:
   print("WAITING_FOR_LOCAL_PRODUCTION",n,"of 20",flush=True)
  time.sleep(18)
 except Exception as e:
  print("UPLOAD_WATCHER_ERROR",str(e)[:350],flush=True)
  time.sleep(27)
else:
 print("UPLOAD_WATCHER_STOPPED_WITHOUT_COMPLETE_BATCH",flush=True)
