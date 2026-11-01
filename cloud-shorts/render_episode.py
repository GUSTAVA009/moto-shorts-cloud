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
from audio_accents import create as make_audio_accents, cover_times
from visual_director import verify_story_subject, directed_plan
from caption_layout import layout_caption
from tts_voice import render as make_voice
from silero_voice import render as make_silero_voice, MODEL_ID as SILERO_MODEL_ID, SPEAKER as SILERO_SPEAKER
from native_bass_voice import render as make_native_bass_voice, VOICE_ENGINE as NATIVE_BASS_ENGINE, SPEAKER as NATIVE_BASS_SPEAKER
from deep_voice import (render as make_real_deep_voice,
                        VOICE_ENGINE as DEEP_ENGINE,
                        PUBLIC_ATTRIBUTION as DEEP_ATTRIBUTION)
from kokoro_voice import render as make_kokoro_voice, MODEL_CARD as KOKORO_MODEL_CARD
from selfhosted_voice import (render as make_selfhosted_voice,
                              VOICE_ENGINE as SELFHOSTED_ENGINE)
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


def validated_music_gain(gain):
    """Quiet music may be necessary for speech; clipping or silencing isn't."""
    level = float(gain)
    if not 0.06 <= level <= 0.34:
        raise ValueError("Unsafe music level requested")
    return level


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
    if len(shots) < 2 or len(shots) > 16:
        raise ValueError("Need 2-16 source shots")
    total = 0.0
    for shot in shots:
        if shot.get("source") not in keys:
            raise ValueError("Unknown footage key")
        start, seconds = float(shot["start"]), float(shot["seconds"])
        if not (0 <= start <= 500 and 1 <= seconds <= 12):
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


MAX_FULL_SOURCE_BYTES = 350_000_000
MAX_SHORT_SOURCE_BYTES = 90_000_000
SOURCE_STREAM_TIMEOUT = 160


def required_source_seconds(episode, source_key):
    """Bound a real source clip to the frames actually needed by this Short."""
    windows = [
        float(shot["start"]) + float(shot["seconds"])
        for shot in episode["shots"] if shot["source"] == source_key
    ]
    if not windows:
        raise ValueError("No visual shot uses licensed source " + source_key)
    declared_duration = float(
        next(x["duration"] for x in episode["footage"] if x["key"] == source_key)
    )
    return round(min(max(windows) + 0.7, declared_duration), 2)


def stream_pexels_excerpt(item, destination, required_seconds, ffmpeg="ffmpeg"):
    """Read only required seconds of a validated Pexels source over HTTPS.

    Never fetch its giant 4K source in full, never invent a file, and keep
    ordinary movement/freeze and license validation on the output.
    """
    checked_source(item)
    if urllib.parse.urlsplit(item["url"]).hostname not in (
            "www.pexels.com", "videos.pexels.com"):
        raise ValueError("Bounded stream only permitted from approved Pexels host")
    duration = float(required_seconds)
    if not 2.0 <= duration <= 40.0:
        raise ValueError("Unsafe requested source excerpt duration")
    cmd = [
        ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
        "-user_agent", "Mozilla/5.0 GUSTAVA-Motorcycle-Shorts/1.0",
        "-i", item["url"], "-map", "0:v:0", "-an",
        "-t", f"{duration:.2f}",
        "-vf", "fps=30,scale=1280:1280:force_original_aspect_ratio=decrease:force_divisible_by=2",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "25",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-f", "mp4", str(destination)
    ]
    try:
        result = subprocess.run(cmd, text=True, capture_output=True,
                                timeout=SOURCE_STREAM_TIMEOUT, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("SOURCE_VIDEO_DOWNLOAD_FAILED: bounded Pexels excerpt timeout") from exc
    if result.returncode or not destination.is_file():
        raise RuntimeError("SOURCE_VIDEO_DOWNLOAD_FAILED: bounded Pexels excerpt: "
                           + (result.stderr or "")[-550:])
    size = destination.stat().st_size
    # Byte count is not a motion or quality metric: a genuine short scene can
    # be less than 250KB after bounded H264 encoding. Keep a strict 80KB
    # corruption floor, verify duration/codec, then independently test movement
    # for every unusually compact source before final per-shot motion QA.
    if not 80_000 <= size <= MAX_SHORT_SOURCE_BYTES:
        raise RuntimeError("SOURCE_VIDEO_DOWNLOAD_FAILED: " + item["key"] +
                           " bounded bytes " + str(size) + " outside 80KB-90MB")
    duration_read, tracks = probe(destination)
    if not any(t.get("codec_type") == "video" for t in tracks):
        raise RuntimeError("SOURCE_VIDEO_DOWNLOAD_FAILED: excerpt has no video")
    # Third-party Pexels catalogs sometimes round or incorrectly declare
    # 8-second clips that are only 6 seconds long. A bounded shortfall may
    # still form a valid two-scene video if the actual moving clip is long
    # enough. NEVER loop, extend, freeze, or forge a source duration; the
    # downstream director makes the final decision from ffprobe durations.
    shortfall=max(0.0,duration-duration_read)
    if shortfall > 0.75:
        if (shortfall>2.25 or shortfall>duration*0.35
                or duration_read<3.5):
            raise RuntimeError("SOURCE_VIDEO_DOWNLOAD_FAILED: excerpt missing required scene time")
        if not motion_verified(destination):
            raise RuntimeError("VISUAL_FROZEN_SEGMENT: shortened source " +
                               item["key"] + " lacks real motion")
        print("SOURCE_ACTUAL_DURATION_RECONCILED",item["key"],
              "requested",round(duration,2),"actual",round(duration_read,2),
              "final director still requires full valid storyboard",flush=True)
    if size < 250_000 and shortfall <= 0.75 and not motion_verified(destination):
        raise RuntimeError("VISUAL_FROZEN_SEGMENT: compact source " +
                           item["key"] + " has no independently verified motion")
    print("LICENSED_PEXELS_SHORT_EXCERPT", item["key"], round(duration_read, 2),
          "seconds", size, "bytes", flush=True)


def download(item, dst, required_seconds=None):
    checked_source(item)
    if dst.is_file() and dst.stat().st_size > 250_000:
        return
    tmp = dst.with_name(dst.stem + ".source.tmp.mp4")
    urlhost = urllib.parse.urlsplit(item["url"]).hostname
    try:
        if urlhost in ("www.pexels.com", "videos.pexels.com"):
            if required_seconds is None:
                raise ValueError("Pexels clip duration must be bounded by episode shot list")
            # The download/video/<id> endpoint may return a >350MB 4K file.
            # FFmpeg seeks/decodes the short source segment remotely and saves
            # an independently QA-checked, low-bandwidth local 720/1280p MP4.
            stream_pexels_excerpt(item, tmp, required_seconds)
        else:
            # Wikimedia Commons CC0 paths are size-audited before admission.
            request = urllib.request.Request(item["url"],
                                             headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=150) as inp, tmp.open("wb") as out:
                while chunk := inp.read(1048576):
                    out.write(chunk)
                    if out.tell() > MAX_FULL_SOURCE_BYTES:
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
    """One shot per real source. No recycled A/B/A/B cuts or sub-3s flashes."""
    durations={}
    for src in ep["footage"]:
        key=src["key"]
        d,streams=probe(sources[key])
        if not any(x.get("codec_type")=="video" for x in streams):
            raise RuntimeError("VISUAL_SOURCE_WITHOUT_VIDEO")
        durations[key]=d
    plan=directed_plan(ep,durations,target_seconds)
    segments=[]
    for idx,shot in enumerate(plan,1):
        src=sources[shot["source"]]
        out=work/("scene_%02d.mp4"%idx)
        run([
            "ffmpeg","-hide_banner","-loglevel","error","-y",
            "-ss","%.3f"%shot["start"],"-i",src,
            "-t","%.3f"%shot["seconds"],
            "-vf","fps=30,scale=720:1280:force_original_aspect_ratio=increase:"
                  "flags=lanczos,crop=720:1280,setsar=1,format=yuv420p",
            "-an","-c:v","libx264","-crf","23","-preset","veryfast",
            "-r","30","-pix_fmt","yuv420p",out,
        ],180)
        if not motion_verified(out):
            out.unlink(missing_ok=True)
            raise RuntimeError(
                "VISUAL_FROZEN_SEGMENT: source "+shot["source"]+
                " is too static. Find another scene, never conceal by fast cuts."
            )
        segments.append(out)
    playlist=work/"playlist.txt"
    playlist.write_text("".join("file '%s'\n"%p.name for p in segments),encoding="utf8")
    silent=work/"assembled.mp4"
    run(["ffmpeg","-hide_banner","-loglevel","error","-y",
         "-f","concat","-safe","0","-i",playlist,
         "-an","-c","copy",silent],120)
    total,_=probe(silent)
    if abs(total-target_seconds)>.36:
        raise RuntimeError("VISUAL_RUNTIME_MISMATCH: wrong finished scene duration")
    qa={
        "version":(3 if int(ep.get("visual_director_version") or 0)>=3 else 2),
        "passed":True,"episode":ep["id"],
        "subject":verify_story_subject(ep)["subject"],
        "source_sequence":[p["source"] for p in plan],
        "sequence":plan,"source_reused_in_short":False,
        "subject_visible_at_start_by_source_metadata":True,
        "note":"Provider source-title matching is only an automated preflight, not a substitute for actually viewing scenes.",
    }
    (work/"visual_qa.json").write_text(
        json.dumps(qa,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print("DIRECTED_SCENES_ASSEMBLED",len(segments),
          "NO_PINGPONG",True,"duration",round(total,2),flush=True)
    return silent,total


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


def safe_caption_display(text):
    """DejaVuSans-Bold has no emoji glyphs: don't burn tofu squares into MP4.

    YouTube title/description retain their original emoji; only video overlay
    text is projected to characters that the bundled font can display.
    Preserve all Cyrillic, words, punctuation and human meaning.
    """
    return "".join(ch for ch in str(text)
                   if ord(ch) <= 0xFFFF and ord(ch) not in (0xFE0F, 0x200D)).strip()


def caption_text_lines(layout):
    """FFmpeg textfile renders literal newline bytes as missing-glyph squares.

    Send each authored caption line to an independent drawtext filter; never
    put a newline into an FFmpeg textfile. Keep width/line-count checks intact.
    """
    lines = str(layout.get("text", "")).splitlines()
    if (len(lines) != layout.get("line_count")
            or not 1 <= len(lines) <= 2
            or any(not line.strip() for line in lines)):
        raise ValueError("CAPTION_LINES_INVALID")
    return lines


def caption_schedule(ep, total, planned_scenes=None):
    """Match an ironic myth/reveal caption to the *actual* footage cut.

    Previously every second caption appeared at ~3.9s, often several seconds
    before the real travel-to-racetrack transition; a generic fixed timer
    therefore made captions feel unrelated to the video.
    """
    start = ("caption_start", 0.05, min(2.45, total - 4.0))
    finish = ("caption_end", total - 2.75, total - 0.12)
    if ep.get("creative_treatment") != "myth_vs_reality_irony":
        spans = [start]
        if not ep.get("story_steps"):
            spans.append(("caption_middle", min(3.9, total - 4.0),
                          min(6.35, total - 2.8)))
        return spans + [finish]
    if (not isinstance(planned_scenes, list) or len(planned_scenes) != 2
            or any(not isinstance(item, dict) for item in planned_scenes)):
        raise RuntimeError("MYTH_CAPTION_REQUIRES_VERIFIED_TWO_SHOT_PLAN")
    try:
        cut = float(planned_scenes[0]["seconds"]) - float(
            ep.get("opening_trim_seconds", 0.0))
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise RuntimeError("MYTH_CAPTION_TRANSITION_UNVERIFIED") from error
    if not 3.5 < cut < total - 3.6:
        raise RuntimeError("MYTH_CAPTION_CUT_OUTSIDE_READABLE_DURATION")
    # The comparison text appears only AFTER the second real source begins,
    # never over unrelated B-roll from the first scene.
    reveal_at = cut + 0.12
    reveal_until = min(reveal_at + 2.35, total - 3.05)
    if reveal_until - reveal_at < 1.0:
        raise RuntimeError("MYTH_CAPTION_REVEAL_TOO_SHORT")
    return [start, ("caption_middle", reveal_at, reveal_until), finish]


def draw_captions(ep, work, total):
    if not FONT.is_file():
        raise RuntimeError("Expected Cyrillic font not present")
    plan = None
    if ep.get("creative_treatment") == "myth_vs_reality_irony":
        qa_path = work / "visual_qa.json"
        if not qa_path.is_file():
            raise RuntimeError("MYTH_CAPTION_MISSING_REAL_VISUAL_QA")
        visual_qa = json.loads(qa_path.read_text(encoding="utf8"))
        if (visual_qa.get("passed") is not True
                or visual_qa.get("episode") != ep.get("id")):
            raise RuntimeError("MYTH_CAPTION_VISUAL_QA_MISMATCH")
        plan = visual_qa.get("sequence")
    spans = caption_schedule(ep, total, plan)
    filters = []
    caption_checks = []

    def add_caption(label, text, at, until, index):
        if until <= at:
            return
        text = safe_caption_display(text)
        layout = layout_caption(text, font_path=FONT)
        lines = caption_text_lines(layout)
        filters.append(
            ("drawbox=x=23:y=%d:w=674:h=%d:color=black@0.50:t=fill:"
             "enable='between(t,%.3f,%.3f)'") %
            (layout["box_y"], layout["box_height"], at, until)
        )
        for line_index, one_line in enumerate(lines):
            caption_file = work / ("subtitle_%02d_%d.txt" % (index, line_index))
            caption_file.write_text(one_line, encoding="utf-8")
            # Both text lines remain inside the pre-measured black safe box.
            y = layout["text_y"] + line_index * round(layout["font_size"] * 1.30)
            filters.append(
                ("drawtext=fontfile=%s:textfile=%s:fontsize=%d:fontcolor=white:"
                 "shadowcolor=black@0.95:shadowx=2:shadowy=2:"
                 "x=(w-text_w)/2:y=%d:enable='between(t,%.3f,%.3f)'") %
                (FONT, caption_file, layout["font_size"], y, at, until)
            )
        caption_checks.append({"label": label, "font_size": layout["font_size"],
                               "line_count": layout["line_count"],
                               "starts_at_seconds": round(at, 3),
                               "ends_at_seconds": round(until, 3),
                               "max_line_width_px": layout["max_line_width_px"],
                               "safe_width_px": layout["safe_width_px"]})

    for i, (field, lo, hi) in enumerate(spans):
        add_caption(field, ep[field], lo, hi, i)
    for j, (beat_text, at, until) in enumerate(fitted_story_beats(ep, total)):
        add_caption("story_beat_%d" % j, beat_text, at, until, j + len(spans))
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
    (work / "caption_fit.json").write_text(json.dumps({
        "version": 1, "passed": bool(caption_checks),
        "entries": caption_checks,
    }, ensure_ascii=False, indent=2), encoding="utf8")
    filters.append("fade=t=out:st=%.2f:d=0.30" % max(0, total - 0.30))
    return ",".join(filters)


def render(ep, output_dir):
    slug = validate_episode(ep)
    # Reject helmet/repair guides without any clearly matching actual source.
    # Checking unrelated "topics" tags was the cause of the failed helmet Short.
    subject_report = verify_story_subject(ep)
    print("VISUAL_SUBJECT_PREFLIGHT", subject_report, flush=True)
    work = HERE / "work" / slug
    work.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = {}
    for src in ep["footage"]:
        video_id = checked_source(src)
        if video_id.startswith("commons-"):
            verified_commons(src)
        target = work / (video_id + ".mp4")
        download(src, target, required_seconds=required_source_seconds(ep, src["key"]))
        sources[src["key"]] = target

    wav = work / "new_narration.wav"
    engine = ep.get("voice_engine", "piper_ru")
    if engine == DEEP_ENGINE:
        voice_duration = make_real_deep_voice(ep, wav)
        engine_label = "AI Doc Maker Create Audio Voice / deep (original approved preset)"
    elif engine == SELFHOSTED_ENGINE:
        voice_duration = make_selfhosted_voice(ep, wav)
        engine_label = "GUSTAVA Original / private Qwen3-TTS API (SHA-pinned)"
    elif engine == "kokoro_ru_dima":
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
    (output_dir/"visual_qa.json").write_bytes((work/"visual_qa.json").read_bytes())
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
    accents = work / "original_audio_accents.wav"
    cue_report = make_audio_accents(accents,total,style=music_style,seed=music_seed)
    print("ORIGINAL_SOUND_DESIGN_READY", cue_report, flush=True)
    captions = draw_captions(ep, work, total)

    output = output_dir / (slug + ".mp4")
    mix_gain = validated_music_gain(os.environ.get("GUSTAVA_MUSIC_GAIN", "0.18"))
    filter_graph = (
        "[0:v]" + captions + "[v];"
        "[1:a]aresample=48000,highpass=f=85,lowpass=f=8900,"
        "volume=1.00,adelay=160|160,apad,atrim=duration=%.3f,"
        "asetpts=PTS-STARTPTS,aformat=channel_layouts=stereo,asplit=2[voice_duck][voice_mix];" % total
        + f"[2:a]aresample=48000,volume={mix_gain:.2f},"
        "afade=t=in:st=0:d=0.18,afade=t=out:st=%.3f:d=0.4,"
        "atrim=duration=%.3f,asetpts=PTS-STARTPTS,"
        "aformat=channel_layouts=stereo,haas=side_gain=0.55[bed];" % (max(0.1, total - 0.4), total)
        + "[3:a]aresample=48000,volume=0.22,"
          "aformat=channel_layouts=stereo,atrim=duration=%.3f[fx];" % total
        + "[bed][fx]amix=inputs=2:duration=first:normalize=0[soundbed];"
        + "[soundbed][voice_duck]sidechaincompress=threshold=0.022:"
        "ratio=7:attack=8:release=240[ducked];"
        "[ducked][voice_mix]amix=inputs=2:duration=first:normalize=0,"
        "volume=6dB,alimiter=limit=0.92[a]"
    )
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", silent, "-i", wav, "-i", soundtrack, "-i", accents,
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
    # QA was previously blind to text extending outside the portrait frame.
    # Only the NEW render receives this proof; existing clipped artifacts
    # remain ineligible for auto-publication until genuinely corrected.
    caption_report = json.loads((work / "caption_fit.json").read_text(encoding="utf8"))
    if (caption_report.get("version") != 1 or caption_report.get("passed") is not True
            or not caption_report.get("entries")):
        raise RuntimeError("CAPTION_FIT_QA_NOT_VERIFIED")
    visual_path = output_dir / "visual_qa.json"
    visual_payload = json.loads(visual_path.read_text(encoding="utf8"))
    visual_payload.update(caption_layout_version=1, caption_fit_passed=True,
                          caption_layouts=caption_report["entries"])
    visual_path.write_text(json.dumps(visual_payload, ensure_ascii=False, indent=2),
                           encoding="utf8")
    # Covers must be extracted from this exact rendered episode, never
    # scraped from another creator or made to depict unrelated events.
    times = cover_times(total)
    for index, at in enumerate(times, start=1):
        name = "thumbnail.jpg" if index == 1 else "thumbnail_candidate_%d.jpg" % index
        run(["ffmpeg","-hide_banner","-nostdin","-loglevel","error","-y",
             "-ss",f"{at:.2f}","-i",output,"-frames:v","1",
             output_dir/name],35)
    (output_dir/"thumbnail_candidates.json").write_text(
        json.dumps({"episode_id":slug,"frame_times":times,
                    "source":"OWN_NEW_RENDERED_VIDEO",
                    "selection":"YouTube Studio -> Edit Short -> Thumbnail / Choose from video",
                    "note":"Choosing/uploading a custom Shorts thumbnail requires account support."},
                   ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    publication = {
        "title": ep["title"],
        "description": (clean_description(build_description(ep))
                        + ("\n\n" + DEEP_ATTRIBUTION if engine == DEEP_ENGINE else "")),
        "tags": ep.get("tags", ["мото", "shorts"]),
        "status": "REVIEW_REQUIRED",
        "youtube_published": False,
        "duration_seconds": round(duration, 2),
        "voice_engine": engine_label,
        "audio_source": ("Exact approved AI Doc Maker deep recording, original music and SFX"
                         if engine == DEEP_ENGINE else
                         "Fresh synthesized narration, original procedural music and original SFX"),
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
        "voice_model_card": ("https://www.aidocmaker.com/" if engine == DEEP_ENGINE
            else "https://github.com/QwenLM/Qwen3-TTS" if engine == SELFHOSTED_ENGINE

            else KOKORO_MODEL_CARD if engine == "kokoro_ru_dima"
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
