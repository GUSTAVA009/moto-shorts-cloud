"""GUSTAVA production-only visual resolution contract.

Native 2K portrait is 1440x2560; UHD portrait is 2160x3840.
An upscaled 448x800 original is not true 2K detail. The *actual* decoded
source must satisfy this guard before any expensive render or publication.
"""
from pathlib import Path
import json
import subprocess

MIN_WIDTH=1440
MIN_HEIGHT=2560
MAX_WIDTH=2160
MAX_HEIGHT=3840

def visual_dimensions(path):
    video=Path(path)
    if not video.is_file():
        raise ValueError("NATIVE_2K_SOURCE_FILE_MISSING")
    try:
        run=subprocess.run(
            ["ffprobe","-v","error","-select_streams","v:0",
             "-show_entries","stream=width,height","-of","json",str(video)],
            capture_output=True,text=True,check=True,timeout=20)
        info=json.loads(run.stdout)["streams"][0]
        return int(info["width"]),int(info["height"])
    except (OSError,ValueError,IndexError,KeyError,TypeError,
            subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
        raise ValueError("NATIVE_2K_VIDEO_PROBE_FAILED") from exc

def available_portrait_crop(width,height):
    """How many source pixels survive a centered 9:16 vertical reframe."""
    if width <= 0 or height <= 0:
        raise ValueError("NATIVE_2K_INVALID_SOURCE_RESOLUTION")
    if width*16 >= height*9:
        return (height*9//16,height)
    return (width,width*16//9)

def require_native_source(path):
    width,height=visual_dimensions(path)
    crop_w,crop_h=available_portrait_crop(width,height)
    if crop_w<MIN_WIDTH or crop_h<MIN_HEIGHT:
        raise ValueError(
            f"NATIVE_2K_SOURCE_REQUIRED: actual {width}x{height}; "
            f"portrait crop {crop_w}x{crop_h}, minimum {MIN_WIDTH}x{MIN_HEIGHT}; "
            "NO_FAKE_UPSCALE")
    return width,height

def require_native_final(path):
    width,height=visual_dimensions(path)
    if (width,height) not in ((1440,2560),(2160,3840)):
        raise ValueError(
            f"FINAL_SHORTS_2K_OR_4K_REQUIRED: got {width}x{height}; "
            "required native 1440x2560 or 2160x3840; NO_FAKE_UPSCALE")
    return width,height
