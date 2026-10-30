#!/usr/bin/env python3
"""New original voice, scene cuts, music and subtitles for every episode.

All source video clips come from their external Pexels download URLs.
Never scans the operator's computer, reuses the published first video, or
uploads to YouTube from this renderer.
"""
from __future__ import annotations
import argparse
import hashlib
import os
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.parse
import urllib.request

from soundtrack import generate as make_music
from tts_voice import render as make_voice
from silero_voice import render as make_silero_voice, MODEL_ID as SILERO_MODEL_ID, SPEAKER as SILERO_SPEAKER
from native_bass_voice import render as make_native_bass_voice, VOICE_ENGINE as NATIVE_BASS_ENGINE, SPEAKER as NATIVE_BASS_SPEAKER
from kokoro_voice import render as make_kokoro_voice, MODEL_CARD as KOKORO_MODEL_CARD
from editorial_guard import validate_catalog
from moto_assets import validated_media, verified_commons
from channel_focus import assert_motorcycle_episode
from engagement_cta import validate_cta, overlay_filters, build_description

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
    """Never render an unlicensed, unauthenticated or unsupported source."""
    return validated_media(item)


def validate_episode(ep):
    slug = ep.get("id", "")
    if not ID.fullmatch(slug):
        raise ValueError("Invalid episode ID")
    if ep.get("auto_preview") is True or ep.get("auto_publish") is True:
        assert_motorcycle_episode(ep)
    for field in ("title", "narration", "description", "caption_start", "caption_middle", "caption_end"):
        value = str(ep.get(field, "")).strip()
        if not value or any(term in value.casefold() for term in BAN):
            raise ValueError("Missing or disallowed public field: " + field)
    if len(ep["title"]) > 100 or len(ep["narration"]) > 350:
        raise ValueError("Title/narration too long")
    max_duration = float(ep.get("max_duration_seconds", 19.5))
    if not 9.0 <= max_duration <= 36.0:
        raise ValueError("Story video max duration must be between 9 and 36 seconds")
    story_steps = ep.get("story_steps", [])
    if not isinstance(story_steps, list) or len(story_steps) > 4:
        raise ValueError("At most four original story beat captions")
    previous_at = 0.0
    for item in story_steps:
        t = float(item.get("at", -1))
        caption = str(item.get("text", "")).strip()
        if not (2.5 <= t <= max_duration - 2.7) or t <= previous_at + 1.0:
            raise ValueError("Invalid or overlapping story beat time")
        if not (4 <= len(caption) <= 29) or any(bad in caption.casefold() for bad in BAN):
            raise ValueError("Invalid original story beat title")
        previous_at = t
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
        if media.get("license") not in ("Pexels License", "CC0 1.0") or not media.get("author"):
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
    validate_cta(ep)
    opening_trim = float(ep.get("opening_trim_seconds", 0.0))
    if not 0 <= opening_trim <= 2.0:
        raise ValueError("Action hook trim must be between 0 and 2 seconds")
    return slug


def load_episode(path, slug):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_catalog(raw)  # Fail before fetching any footage if previously used source appears.
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


def motion_verified(path, threshold_seconds=1.25):
    """Refuse real frozen source shots, rather than fooling final freeze QA with cuts."""
    check = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-an",
         "-vf", "freezedetect=n=-45dB:d=%.2f" % threshold_seconds,
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=40,
    )
    if check.returncode:
        raise RuntimeError("Could not run independent per-shot motion QA")
    return "freeze_start:" not in check.stderr


def assemble_clips(ep, sources, work, target_seconds):
    remaining = target_seconds
    segments = []
    shots = ep["shots"]
    accepted_sources = set()
    tried = 0
    # Try alternate shots when a licensed source has a truly frozen section.
    # Repeated stills are NOT silently allowed as multiple short cuts.
    while remaining > 0.30 and tried < 48 and len(segments) < 18:
        shot = shots[tried % len(shots)]
        tried += 1
        src = sources[shot["source"]]
        src_duration, streams = probe(src)
        if not any(s["codec_type"] == "video" for s in streams):
            raise RuntimeError("Downloaded source lacks video")
        start = float(shot["start"])
        seconds = min(float(shot["seconds"]), remaining, src_duration - start - 0.1)
        if seconds < 0.9:
            start = max(0.0, src_duration - min(2.5, remaining) - 0.2)
            seconds = min(float(shot["seconds"]), remaining, src_duration - start - 0.1)
        if seconds < 0.28:
            continue
        out = work / ("scene_%02d.mp4" % tried)
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{start:.3f}", "-i", src, "-t", f"{seconds:.3f}",
            "-vf", "fps=30,scale=720:1280:force_original_aspect_ratio=increase:"
                   "flags=lanczos,crop=720:1280,setsar=1,format=yuv420p",
            "-an", "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
            "-r", "30", "-pix_fmt", "yuv420p", out,
        ], 180)
        if seconds > 1.35 and not motion_verified(out):
            out.unlink(missing_ok=True)
            print("FROZEN_SOURCE_SHOT_REJECTED", shot["source"],
                  "offset", round(start, 2), flush=True)
            continue
        segments.append(out)
        accepted_sources.add(shot["source"])
        remaining -= seconds
    if remaining > 0.35 or len(accepted_sources) < 2:
        raise RuntimeError(
            "NOT_ENOUGH_MOVING_LICENSED_SCENES: video release blocked, "
            "new footage or corrected shot offsets required"
        )
    playlist = work / "playlist.txt"
    playlist.write_text("".join("file '%s'\n" % p.name for p in segments), encoding="utf-8")
    silent = work / "assembled.mp4"
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", playlist,
        "-an", "-c", "copy", silent,
    ], 120)
    total, _ = probe(silent)
    print("SCENES_ASSEMBLED", len(segments), "unique_sources", len(accepted_sources),
          "discarded_still_shots", tried - len(segments),
          "seconds", round(total, 2), flush=True)
    return silent, total


def fitted_story_beats(ep, total):
    """Place authored explanation beats within the actual synthesized narration.

    Static time marks can exceed real TTS duration. Never silently drop the
    third fact or overlap the closing question and lower-third.
    """
    steps = ep.get("story_steps", [])
    if not steps:
        return []
    start = 3.05
    end = total - 3.35
    step = (end - start) / len(steps)
    if step < 1.45:
        raise RuntimeError("Narration too short for all fact captions; revise script")
    result = []
    for index, item in enumerate(steps):
        begin = start + index * step
        until = min(end, begin + min(2.45, step - 0.20))
        result.append((item["text"], begin, until))
    return result


def draw_captions(ep, work, total):
    if not FONT.is_file():
        raise RuntimeError("Expected Cyrillic font not present")
    spans = [
        ("caption_start", 0.05, min(2.45, total - 4.0)),
    ]
    # Fact explanations take the middle of a story-driven Short. Do not
    # place generic middle captions on top of the factual sequence.
    if not ep.get("story_steps"):
        spans.append(("caption_middle", min(3.9, total - 4.0), min(6.35, total - 2.8)))
    spans.append(("caption_end", total - 2.75, total - 0.12))
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
    # New, longer narrative Shorts can display independently authored,
    # time-coded factual beats rather than silent slides or recycled templates.
    for j, (beat_text, at, until) in enumerate(fitted_story_beats(ep, total)):
        beat_file = work / ("story_beat_%02d.txt" % j)
        beat_file.write_text(beat_text, encoding="utf-8")
        filters.extend([
            "drawbox=x=23:y=126:w=674:h=92:color=black@0.45:t=fill:"
            "enable='between(t,%.3f,%.3f)'" % (at,until),
            "drawtext=fontfile=%s:textfile=%s:fontsize=34:fontcolor=white:"
            "shadowcolor=black@0.95:shadowx=2:shadowy=2:"
            "x=(w-text_w)/2:y=154:enable='between(t,%.3f,%.3f)'"
            % (FONT, beat_file, at, until),
        ])
    # Documentary chapters use separately licensed, present-day illustration,
    # NEVER archival footage of their real historical protagonist.
    if ep.get("episode_series", {}).get("historical_reconstruction") is True:
        disclosure = work / "historical_illustration_label.txt"
        disclosure.write_text("ИЛЛЮСТРАТИВНЫЕ КАДРЫ", encoding="utf8")
        filters.extend([
            "drawbox=x=25:y=238:w=480:h=52:color=black@0.60:t=fill",
            "drawtext=fontfile=%s:textfile=%s:fontsize=22:fontcolor=white:"
            "borderw=1:bordercolor=black@0.8:x=44:y=252" % (FONT, disclosure),
        ])
    # Quiet lower-third CTA rotates per episode; story and final question remain readable.
    filters.extend(overlay_filters(ep, work, total, FONT))
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
        if video_id.startswith("commons-"):
            verified_commons(src)
        target = work / (video_id + ".mp4")
        download(src, target)
        sources[src["key"]] = target

    wav = work / "new_narration.wav"
    engine = ep.get("voice_engine", "piper_ru")
    if engine == "kokoro_ru_dima":
        retry_speed = float(os.environ.get("GUSTAVA_TTS_SPEED", "1.0"))
        voice_duration = make_kokoro_voice(ep["narration"], wav, work / "kokoro_model", speed=retry_speed)
        engine_label = "Kokoro-RU / dima (OpenRAIL, CPU Russian male narrator)"
    elif engine == NATIVE_BASS_ENGINE:
        speed = float(os.environ.get("GUSTAVA_TTS_SPEED", "1.0"))
        voice_duration = make_native_bass_voice(
            ep["narration"], wav, work / "voice_model", speed=speed)
        engine_label = "Silero MIT V5 CIS / ru_alexandr (native clean male bass-baritone)"
    elif engine == "silero_cis_base_mit":
        voice_duration = make_silero_voice(ep["narration"], wav, work / "voice_model")
        engine_label = "Silero " + SILERO_MODEL_ID + " / " + SILERO_SPEAKER + " (MIT)"
    elif engine == "piper_ru":
        voice_duration = make_voice(ep["narration"], wav, work / "voice_model")
        engine_label = "Piper ru_RU-denis-medium (CC0 training set)"
    else:
        raise ValueError("Unknown or noncommercial voice engine")
    # Speech drives the duration; no long silent post-narration section.
    requested = max(9.0, min(float(ep.get("max_duration_seconds", 19.5)), voice_duration + 1.25))
    if voice_duration > requested - 0.75:
        raise RuntimeError("Voice too long for video, shorten the original narration")
    silent, total = assemble_clips(ep, sources, work, requested)
    # Cut blank establishing footage BEFORE the speech, music, and captions
    # are mixed. Start with visible action rather than an empty hill/track.
    opening_trim = float(ep.get("opening_trim_seconds", 0.0))
    if opening_trim > 0:
        if total - opening_trim < max(7.0, voice_duration + 0.70):
            raise RuntimeError("Opening trim would cut off the narration")
        action_first = work / "action_first.mp4"
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{opening_trim:.3f}", "-i", silent,
            "-t", f"{total - opening_trim:.3f}", "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-pix_fmt", "yuv420p", "-r", "30", action_first,
        ], 180)
        silent = action_first
        total, _ = probe(silent)
        print("ACTION_HOOK_TRIM", opening_trim, "new duration", round(total, 2), flush=True)
    soundtrack = work / "original_instrumental.wav"
    music_style = ep.get("music_style", "action")
    # Per-episode seed prevents the same instrumental playing underneath
    # different scenes, even when their music genre is similar.
    music_seed = int(hashlib.sha256(slug.encode("utf8")).hexdigest()[:8], 16)
    make_music(soundtrack, total, bpm=int(ep.get("music_bpm", 128)),
               style=music_style, seed=music_seed)
    captions = draw_captions(ep, work, total)

    output = output_dir / (slug + ".mp4")
    mix_gain = float(os.environ.get("GUSTAVA_MUSIC_GAIN", "0.18"))
    if not 0.12 <= mix_gain <= 0.34:
        raise ValueError("Unsafe music level requested")
    filter_graph = (
        "[0:v]" + captions + "[v];"
        "[1:a]aresample=48000,highpass=f=85,lowpass=f=8900,"
        "volume=1.00,adelay=160|160,apad,atrim=duration=%.3f,"
        "asetpts=PTS-STARTPTS,aformat=channel_layouts=stereo,asplit=2[voice_duck][voice_mix];" % total
        + f"[2:a]aresample=48000,volume={mix_gain:.2f},"
        "afade=t=in:st=0:d=0.18,afade=t=out:st=%.3f:d=0.4,"
        "atrim=duration=%.3f,asetpts=PTS-STARTPTS,"
        "aformat=channel_layouts=stereo,haas=side_gain=0.55[bed];" % (max(0.1, total - 0.4), total)
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
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-t", f"{total:.3f}", output,
    ], 270)
    duration, streams = probe(output)
    if not (7 <= duration <= 37) or not (output.stat().st_size > 500_000):
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
        "description": clean_description(build_description(ep)),
        "tags": ep.get("tags", ["мото", "shorts"]),
        "status": "REVIEW_REQUIRED",
        "youtube_published": False,
        "duration_seconds": round(duration, 2),
        "voice_engine": engine_label,
        "audio_source": "Fresh synthesized narration and original procedural music",
        "music_style": music_style,
        "editorial_profile": ep.get("editorial"),
        "episode_id": slug,
        "engagement_cta": {"kind": ep["cta"]["kind"], "overlay": ep["cta"]["overlay"]},
    }
    (output_dir / "publication.json").write_text(
        json.dumps(publication, ensure_ascii=False, indent=2), encoding="utf8"
    )
    # Attribution and source pages remain INTERNAL, never part of YouTube description.
    receipt = {
        "episode": slug,
        "license_sources": ep["footage"],
        "editorial_references": ep.get("editorial_references", []),
        "voice_model_card": (KOKORO_MODEL_CARD if engine == "kokoro_ru_dima"
            else "https://github.com/snakers4/silero-models" if engine in ("silero_cis_base_mit", NATIVE_BASS_ENGINE)
            else "https://huggingface.co/rhasspy/piper-voices/blob/main/ru/ru_RU/denis/medium/MODEL_CARD"),
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
