"""Production-grade source metadata gate before ANY immutable MP4 reservation.

SHA-pinned licensed original footage is required for native 2K/4K Shorts.
Metadata is only a preflight: render_episode verifies every source's real
decoded pixels and SHA after download. No fake upscales or inference from tags.
"""
from __future__ import annotations
import re
import urllib.parse
from production_quality import export_dimensions, available_portrait_crop

SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
ALLOWED_HOSTS = {"www.pexels.com", "videos.pexels.com"}
MAX_SOURCE_BYTES = 350_000_000


def source_proof(source, profile="2k"):
    if not isinstance(source,dict):
        raise ValueError("NATIVE_2K_SOURCE_METADATA_INVALID")
    req_w,req_h=export_dimensions(profile)
    if source.get("license") != "Pexels License" or not source.get("author"):
        raise ValueError("NATIVE_2K_LICENSE_NOT_VERIFIED")
    parsed=urllib.parse.urlsplit(str(source.get("url") or ""))
    if (parsed.scheme!="https" or parsed.hostname not in ALLOWED_HOSTS
        or parsed.username or parsed.password or parsed.port not in (None,443)):
        raise ValueError("NATIVE_2K_URL_NOT_APPROVED")
    if source.get("key") not in ("clip_0","clip_1"):
        raise ValueError("NATIVE_2K_SOURCE_KEY_INVALID")
    families=[]
    for kind,dim in (("4k",(2160,3840)),("2k",(1440,2560))):
        fields=["native_"+kind+"_"+suffix for suffix in
                ("sha256","bytes","width","height")]
        present=[x in source for x in fields]
        if any(present):
            if not all(present):
                raise ValueError("NATIVE_2K_SOURCE_FINGERPRINT_PARTIAL")
            families.append((kind,dim,fields))
    if len(families)!=1:
        raise ValueError("NATIVE_2K_SOURCE_PROOF_MISSING_OR_AMBIGUOUS")
    kind,(w,h),fields=families[0]
    hashval,bytecount,width,height=(source[key] for key in fields)
    if not isinstance(hashval,str) or SHA_RE.fullmatch(hashval) is None:
        raise ValueError("NATIVE_2K_SOURCE_SHA_INVALID")
    if type(bytecount) is not int or not 1_000_000<=bytecount<=MAX_SOURCE_BYTES:
        raise ValueError("NATIVE_2K_SOURCE_BYTES_INVALID")
    if (type(width) is not int or type(height) is not int
            or not 640<=width<=8192 or not 640<=height<=8192):
        raise ValueError("NATIVE_2K_SOURCE_PIXELS_NOT_PROVEN")
    crop_w,crop_h=available_portrait_crop(width,height)
    # Preserve the ACTUAL source dimensions, including 2160x4096 videos
    # that can be cropped to 2160x3840 without inventing a single pixel.
    required_crop=(2160,3840) if kind=="4k" else (1440,2560)
    if crop_w<required_crop[0] or crop_h<required_crop[1]:
        raise ValueError("NATIVE_2K_SOURCE_PIXELS_NOT_PROVEN")
    if crop_w<req_w or crop_h<req_h:
        raise ValueError("NATIVE_4K_SOURCE_REQUIRED_FOR_4K_PROFILE")
    return {"sha256":hashval,"bytes":bytecount,
            "width":width,"height":height,"profile":kind}


def require_native_sources(episode,profile="2k"):
    originals=episode.get("footage") or []
    if len(originals)!=2:
        raise ValueError("NATIVE_2K_TWO_ACTION_SCENES_REQUIRED")
    proofs=[source_proof(x,profile) for x in originals]
    return proofs
