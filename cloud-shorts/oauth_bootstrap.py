#!/usr/bin/env python3
"""One-time OAuth authorization. Never prints tokens or stores them in this repository."""
from pathlib import Path
import argparse
import stat

SCOPES=[
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
p=argparse.ArgumentParser()
p.add_argument("--google-client-json", type=Path, required=True)
p.add_argument("--output", type=Path,
               default=Path.home()/".youtube-direct-uploader"/"refresh-token.txt")
args=p.parse_args()
if not args.google_client_json.is_file():
    raise SystemExit("Download OAuth Desktop client JSON from Google Cloud first.")
from google_auth_oauthlib.flow import InstalledAppFlow
flow=InstalledAppFlow.from_client_secrets_file(str(args.google_client_json),SCOPES)
creds=flow.run_local_server(port=0,access_type="offline",prompt="consent")
if not creds.refresh_token:
    raise SystemExit("Google did not return a refresh token; check consent screen.")
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(creds.refresh_token+"\n",encoding="utf-8")
try:
    args.output.chmod(stat.S_IRUSR|stat.S_IWUSR)
except OSError:
    pass
print("OAuth complete. Refresh token stored privately at:",args.output)
print("Add it as a GitHub Actions secret YOUTUBE_REFRESH_TOKEN. NEVER paste it in chat.")
