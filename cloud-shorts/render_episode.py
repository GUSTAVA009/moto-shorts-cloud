#!/usr/bin/env python3
"""New original voice, scene cuts, music and subtitles for every episode.

All source video clips come from their external Pexels download URLs.
Never scans the operator's computer, reuses the published first video, or
uploads to YouTube from this renderer.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.parse
import urllib.request

from soundtrack import generate as make_music
from tts_voice import render as make_voice

HERE = Path(__file__).resolve().parent
EPISODES = HERE / "episodes.json"
ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,46}$")
BAN = ("хапыч", "эндуро")
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def run(cmd, timeout=240):
    result = subprocess.run(
        [str(x) for x in cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(
            "FFmpeg/tool failed: " + " ".join(map(str, cmd[:4]))
            + "\n" + result.stderr[-2000:]
        )
    return result.stdout


def probe(path):
    data = json.loads(run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,width,height",
        "-of", "json", path,
    ], 30))
    return float(data["format"]["duration"]), data.get("streams", [])


def clean_description(text):
    return "\n".join(
        ln for ln in str(text).splitlines()
        if "http://" not in ln.lower() and "https://" not in ln.lower()
        and "pexels.com" not in ln.lower()
    ).strip()


def checked_source(item):
    """Validate expected Pexels host and matching video ID (no arbitrary URLs)."""
    page = urllib.parse.urlparse(item["source_page"])
    if page.scheme != "https" or page.hostname != "www.pexels.com":
        raise ValueError("Provenance page must be https://www.pexels.com/video/...")
    match = re.search(r"-(\d{5,10})/?$", page.path)
    if not match or not page.path.startswith("/video/"):
        raise ValueError("Provenance page has no Pexels video ID")
    vid = match.group(1)
    url = urllib.parse.urlparse(item["url"])
    if url.scheme != "https" or url.username or url.password or url.port:
        raise ValueError("Unsupported source URL")
    if url.hostname == "videos.pexels.com":
        if not url.path.startswith("/video-files/" + vid + "/") or not url.path.endswith(".mp4"):
            raise ValueError("Source CDN ID or extension mismatch")
    elif url.hostname == "www.pexels.com":
        if url.path != "/download/video/" + vid + "/":
            raise ValueError("Source download URL must match provenance video ID")
    else:
        raise ValueError("External hosts are forbidden for video downloads")
    return vid


def validate_episode(ep):
    slug = ep.get("id", "")
    if not ID.fullmatch(slug):
        raise ValueError("Invalid episode ID")
    for field in ("title", "narration", "description", "caption_start", "caption_middle", "caption_end"):
        value = str(ep.get(field, "")).strip()
        if not value or any(term in value.casefold() for term in BAN):
            raise ValueError("Missing or disallowed public field: " + field)
    if len(ep["title"]) > 100 or len(ep["narration"]) > 350:
        raise ValueError("Title/narration too long")
    if "http" in ep["description"].lower() or "www." in ep["description"].lower():
        raise ValueError("No URL in YouTube description")
    if not (2 <= len(ep.get("footage", [])) <= 8):
        raise ValueError("Need 2-8 distinct licensed video sources")
    ids = set()
    keys = set()
    for media in ep["footage"]:
        video_id = checked_source(media)
        if video_id in ids or media["key"] in keys:
            raise ValueError("Duplicate source footage")
        ids.add(video_id)
        keys.add(media["key"])
        if media.get("license") != "Pexels License" or not media.get("author"):
            raise ValueError("Source provenance and free license must be recorded")
    shots = ep.get("shots", [])
    if len(shots) < 4 or len(shots) > 16:
        raise ValueError("Need 4-16 shots")
    total = 0.0
    for shot in shots:
        if shot.get("source") not in keys:
            raise ValueError("Unknown footage key")
        start, seconds = float(shot["start"]), float(shot["seconds"])
        if not (0 <= start <= 500 and 1 <= seconds <= 6):
            raise ValueError("Invalid scene offset/duration")
        total += seconds
    if total < 12:
        raise ValueError("Insufficient footage duration")
    return slug


def load_episode(path, slug):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    for ep in raw["episodes"]:
        validate_episode(ep)
        if ep["id"] == slug:
            return ep
    raise ValueError("Unknown episode: " + slug)


def download(item, dst):
    if dst.is_file() and dst.stat().st_size > 250_000:
        return
    request = urllib.request.Request(item["url"], headers={"User-Agent": "Mozilla/5.0"})
    tmp = dst.with_suffix(".download")
    try:
        with urllib.request.urlopen(request, timeout=150) as inp, tmp.open("wb") as out:
            while chunk := inp.read(1048576):
                out.write(chunk)
                if out.tell() > 350_000_000:
                    raise RuntimeError("Too much video data from a single source")
        if tmp.stat().st_size < 250_000:
            raise RuntimeError("Source video download was empty or too small")
        tmp.replace(dst)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    print("FOOTAGE_DOWNLOADED", item["key"], dst.stat().st_size, flush=True)


def assemble_clips(ep, sources, work, target_seconds):
    remaining = target_seconds
    segments = []
    shots = ep["shots"]
    scene_count = 0
    while remaining > 0.07 and scene_count < 18:
        shot = shots[scene_count % len(shots)]
        src = sources[shot["source"]]
        src_duration, streams = probe(src)
        if not any(s["codec_type"] == "video" for s in streams):
            raise RuntimeError("Downloaded source lacks video")
        start = float(shot["start"])
        seconds = min(float(shot["seconds"]), remaining, src_duration - start - 0.1)
        if seconds < 0.9:
            # Some Pexels previews are only a few seconds long. Reframe inside
            # their real runtime rather than requesting nonexistent frames.
            start = max(0.0, src_duration - min(2.5, remaining) - 0.2)
            seconds = min(float(shot["seconds"]), remaining, src_duration - start - 0.1)
        if seconds < 0.8:
            raise RuntimeError("Source too short for any valid cut: " + shot["source"])
        out = work / ("scene_%02d.mp4" % scene_count)
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{start:.3f}", "-i", src,
            "-t", f"{seconds:.3f}",
            "-vf", "fps=30,scale=720:1280:force_original_aspect_ratio=increase:"
                   "flags=lanczos,crop=720:1280,setsar=1,format=yuv420p",
            "-an", "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
            "-r", "30", "-pix_fmt", "yuv420p", out,
        ], 180)
        segments.append(out)
        remaining -= seconds
        scene_count += 1
    if remaining > 0.25:
        raise RuntimeError("Not enough video scenes for narration")
    playlist = work / "playlist.txt"
    playlist.write_text("".join("file '%s'\n" % p.name for p in segments), encoding="utf-8")
    silent = work / "assembled.mp4"
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", playlist,
        "-an", "-c", "copy", silent,
    ], 120)
    total, _ = probe(silent)
    print("SCENES_ASSEMBLED", len(segments), "seconds", round(total, 2), flush=True)
    return silent, total


def draw_captions(ep, work, total):
    if not FONT.is_file():
        raise RuntimeError("Expected Cyrillic font not present")
    spans = [
        ("caption_start", 0.05, min(2.45, total - 4.0)),
        ("caption_middle", min(3.9, total - 4.0), min(6.35, total - 2.8)),
        ("caption_end", total - 2.75, total - 0.12),
    ]
    filters = []
    for i, (field, lo, hi) in enumerate(spans):
        if hi <= lo:
            continue
        caption_file = work / ("subtitle_%02d.txt" % i)
        caption_file.write_text(ep[field], encoding="utf-8")
        filters.extend([
            "drawbox=x=23:y=126:w=674:h=92:color=black@0.45:t=fill:"
            "enable='between(t,%.3f,%.3f)'" % (lo, hi),
            "drawtext=fontfile=%s:textfile=%s:fontsize=34:fontcolor=white:"
            "shadowcolor=black@0.95:shadowx=2:shadowy=2:"
            "x=(w-text_w)/2:y=154:enable='between(t,%.3f,%.3f)'"
            % (FONT, caption_file, lo, hi),
        ])
    filters.append("fade=t=out:st=%.2f:d=0.30" % max(0, total - 0.30))
    return ",".join(filters)


def render(ep, output_dir):
    slug = validate_episode(ep)
    work = HERE / "work" / slug
    work.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = {}
    for src in ep["footage"]:
        video_id = checked_source(src)
        target = work / (video_id + ".mp4")
        download(src, target)
        sources[src["key"]] = target

    wav = work / "new_narration.wav"
    voice_duration = make_voice(ep["narration"], wav, work / "voice_model")
    # Speech drives the duration; no long silent post-narration section.
    requested = max(9.0, min(19.5, voice_duration + 1.0))
    if voice_duration > requested - 0.25:
        raise RuntimeError("Voice too long for video, shorten the original narration")
    silent, total = assemble_clips(ep, sources, work, requested)
    soundtrack = work / "original_instrumental.wav"
    make_music(soundtrack, total, bpm=int(ep.get("music_bpm", 128)))
    captions = draw_captions(ep, work, total)

    output = output_dir / (slug + ".mp4")
    filter_graph = (
        "[0:v]" + captions + "[v];"
        "[1:a]aresample=48000,highpass=f=85,lowpass=f=8900,"
        "volume=1.15,adelay=160|160,apad,atrim=duration=%.3f,"
        "asetpts=PTS-STARTPTS,asplit=2[voice_duck][voice_mix];" % total
        + "[2:a]aresample=48000,volume=0.46,"
        "afade=t=in:st=0:d=0.18,afade=t=out:st=%.3f:d=0.4,"
        "atrim=duration=%.3f,asetpts=PTS-STARTPTS[bed];" % (max(0.1, total - 0.4), total)
        + "[bed][voice_duck]sidechaincompress=threshold=0.022:"
        "ratio=7:attack=8:release=240[ducked];"
        "[ducked][voice_mix]amix=inputs=2:duration=first:normalize=0,"
        "alimiter=limit=0.92[a]"
    )
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", silent, "-i", wav, "-i", soundtrack,
        "-filter_complex", filter_graph,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-movflags", "+faststart", "-t", f"{total:.3f}", output,
    ], 270)
    duration, streams = probe(output)
    if not (8 <= duration <= 22) or not (output.stat().st_size > 500_000):
        raise RuntimeError("Final MP4 unexpected size/duration")
    if not any(s["codec_type"] == "video" and s.get("width") == 720
               and s.get("height") == 1280 for s in streams):
        raise RuntimeError("Final MP4 must be 720x1280 vertical")
    if not any(s["codec_type"] == "audio" for s in streams):
        raise RuntimeError("Final video missing narration/music audio")
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", "0.8", "-i", output,
        "-frames:v", "1", output_dir / "thumbnail.jpg"
    ], 35)
    publication = {
        "title": ep["title"],
        "description": clean_description(ep["description"]),
        "tags": ["мото", "мотокросс", "shorts"],
        "status": "REVIEW_REQUIRED",
        "youtube_published": False,
        "duration_seconds": round(duration, 2),
        "voice_engine": "piper-tts ru_RU-dmitri-medium, CC0 training set",
        "audio_source": "Fresh synthesized narration and original procedural music",
        "episode_id": slug,
    }
    (output_dir / "publication.json").write_text(
        json.dumps(publication, ensure_ascii=False, indent=2), encoding="utf8"
    )
    # Attribution and source pages remain INTERNAL, never part of YouTube description.
    receipt = {
        "episode": slug,
        "license_sources": ep["footage"],
        "voice_model_card": "https://huggingface.co/rhasspy/piper-voices/blob/main/"
                            "ru/ru_RU/dmitri/medium/MODEL_CARD",
    }
    (output_dir / "license_sources.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf8"
    )
    print("NEW_EPISODE_READY", slug, "seconds", round(duration, 2),
          "bytes", output.stat().st_size, flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--episode", required=True)
    p.add_argument("--catalog", type=Path, default=EPISODES)
    p.add_argument("--out-dir", type=Path, default=HERE / "dist" / "new")
    args = p.parse_args()
    ep = load_episode(args.catalog, args.episode)
    render(ep, args.out_dir / ep["id"])


if __name__ == "__main__":
    main()
