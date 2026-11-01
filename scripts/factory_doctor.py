#!/usr/bin/env python3
"""Read-only PC/CI diagnostics for GUSTAVA Shorts Factory.

Reports configured capabilities and unconsumed candidate stock; does NOT
pretend to check live Buffer posts or generate/publish anything.
Never echoes environment values, API keys, reference WAV or private media.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_VOICE = (
    ("cloud_qwen", "GUSTAVA_SELFHOSTED_TTS_ENABLED", "GUSTAVA_VOICE_API_KEY",
     "GUSTAVA_VOICE_API_URL", "GUSTAVA_VOICE_APPROVED_HOST"),
    ("local_windows_qwen", "GUSTAVA_LOCAL_TTS_ENABLED", "GUSTAVA_LOCAL_VOICE_API_KEY",
     "GUSTAVA_LOCAL_VOICE_API_URL", "GUSTAVA_LOCAL_VOICE_APPROVED_HOST"),
    ("third_chatterbox", "GUSTAVA_TERTIARY_TTS_ENABLED", "GUSTAVA_TERTIARY_VOICE_API_KEY",
     "GUSTAVA_TERTIARY_VOICE_API_URL", "GUSTAVA_TERTIARY_VOICE_APPROVED_HOST"),
)


def audit(root=ROOT, env=None):
    """No network, no subprocesses, no runtime secrets in returned output."""
    env = os.environ if env is None else env
    root = Path(root)
    sys.path.insert(0, str(root / "cloud-shorts"))
    from moto_assets import source_id
    from source_story import select_pair

    pool=json.loads((root/"cloud-shorts/verified_pexels_pool.json").read_text("utf8"))
    catalog=json.loads((root/"cloud-shorts/episodes.json").read_text("utf8"))
    sources=pool["sources"]
    episodes=catalog["episodes"]
    used={source_id(f) for ep in episodes for f in ep.get("footage",[])}
    unseen=[f for f in sources if source_id(f) not in used]
    pair_themes={}
    for theme in sorted({t for f in unseen for t in f.get("topics",[])}):
        pair=select_pair([f for f in unseen if theme in f.get("topics",[])],used)
        pair_themes[theme]=len(pair)==2
    voices={}
    for name,enable,key,url,hostname in PUBLIC_VOICE:
        ready=bool(env.get(enable)=="1" and env.get(key)
                   and env.get(url) and env.get(hostname)
                   and env.get("GUSTAVA_VOICE_REFERENCE_SHA256"))
        # Configured is never the same as a live, voice-matching WAV.
        voices[name]={"configured":ready,"live_wav_verified":None}
    return {
        "checked_at_utc":datetime.now(timezone.utc).isoformat(),
        "mode":"offline_read_only_no_network_calls",
        "python_version":sys.version.split()[0],
        "git_installed":shutil.which("git") is not None,
        "ffmpeg_installed":shutil.which("ffmpeg") is not None,
        "ffprobe_installed":shutil.which("ffprobe") is not None,
        "existing_episode_entries":len(episodes),
        "curated_pexels_source_candidates":len(sources),
        "unused_curated_source_candidates":len(unseen),
        "themes_with_source_action_pair":pair_themes,
        "voice_routes":voices,
        "pexels_api_key_configured":bool(env.get("PEXELS_API_KEY")),
        "buffer_api_key_configured":bool(env.get("BUFFER_API_KEY")),
        "production_mp4_verified":None,
        "buffer_scheduled_live":None,
        "buffer_sent_live":None,
        "youtube_public_shorts_verified":None,
        "not_proof_of_live_publication":True,
    }


def main():
    parser=argparse.ArgumentParser(description="Read-only GUSTAVA Factory diagnosis")
    parser.add_argument("--json",action="store_true",help="machine-readable evidence")
    args=parser.parse_args()
    result=audit()
    if args.json:
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return
    print("GUSTAVA FACTORY - ПРОВЕРКА КОНФИГУРАЦИИ (НЕ ЖИВОЙ ТЕСТ)")
    print("Python:",result["python_version"],"Git:",result["git_installed"],
          "FFmpeg:",result["ffmpeg_installed"])
    print("Каталог:",result["existing_episode_entries"],
          "Источник-кандидаты:",result["curated_pexels_source_candidates"],
          "Новые кандидаты:",result["unused_curated_source_candidates"])
    print("Есть пары разных действий:",sum(result["themes_with_source_action_pair"].values()))
    for name,voice in result["voice_routes"].items():
        print("Озвучка",name,"конфигурация:",voice["configured"],
              "Реальный WAV: НЕ ПРОВЕРЕН")
    print("Buffer и YouTube: НЕ ПРОВЕРЕНЫ. Только live Actions/канал дадут подтверждение.")


if __name__=="__main__":
    main()
