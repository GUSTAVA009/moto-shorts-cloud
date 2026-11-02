"""Strict external footage provenance: licensed Pexels or independently checked CC0.

Pexels existing URLs are kept compatible. Wikimedia Commons files are eligible
ONLY when the Commons API confirms CC0 and the exact original file SHA-1.
No CC-BY/SA or ambiguous jurisdictional public-domain archive clips are used.
"""
from __future__ import annotations
import hashlib
from html import unescape
import json
import re
import urllib.parse
import urllib.request

UA = "GUSTAVA-Enduro-Media-Audit/1.0 (royalty-free video validation)"
PEXELS_ID = re.compile(r"-(\d{5,10})/?$")
MIXKIT_PAGE = re.compile(r"^/free-stock-video/[a-z0-9-]+-(\d{4,7})/$")
MIXKIT_LICENSE = "Mixkit Stock Video Free License"
MIXKIT_LICENSE_PAGE = "https://mixkit.co/license/modal/videoFree/"
COMMONS_SHA1 = re.compile(r"[0-9a-f]{40}$")
MAX_BYTES = 230_000_000


def commons_file_title(item):
    url = urllib.parse.urlsplit(str(item.get("source_page", "")))
    if url.scheme != "https" or url.hostname != "commons.wikimedia.org":
        raise ValueError("Commons provenance must use its official HTTPS file page")
    page_path = urllib.parse.unquote(url.path)
    if not page_path.startswith("/wiki/File:"):
        raise ValueError("Commons provenance must identify a named File page")
    title = page_path.removeprefix("/wiki/").replace("_", " ")
    if ".." in title or "/" in title or len(title) > 290:
        raise ValueError("Malformed Commons file title")
    return title


def source_id(item):
    page = urllib.parse.urlsplit(str(item.get("source_page", "")))
    if page.hostname == "www.pexels.com":
        if page.scheme != "https" or not page.path.startswith("/video/"):
            raise ValueError("Video source must be an official Pexels page")
        match = PEXELS_ID.search(page.path)
        if not match:
            raise ValueError("Missing real Pexels video ID")
        return match.group(1)
    if page.hostname == "mixkit.co":
        match = MIXKIT_PAGE.fullmatch(page.path)
        if page.scheme != "https" or page.query or page.fragment or not match:
            raise ValueError("Mixkit provenance requires exact official Free clip page")
        return "mixkit-" + match.group(1)
    if page.hostname == "commons.wikimedia.org":
        commons_file_title(item)
        sha = str(item.get("commons_sha1", "")).lower()
        if not COMMONS_SHA1.fullmatch(sha):
            raise ValueError("Commons file requires verified immutable SHA-1")
        return "commons-" + sha
    raise ValueError("Unknown footage service; no implicit rights")


def validated_media(item):
    sid = source_id(item)
    raw = str(item.get("url", ""))
    url = urllib.parse.urlsplit(raw)
    if (url.scheme != "https" or url.username or url.password or url.port or
            not item.get("author") or not str(item["author"]).strip()):
        raise ValueError("Missing creator provenance or unsafe media URL")
    if sid.startswith("commons-"):
        if item.get("license") != "CC0 1.0":
            raise ValueError("Commons license must be independently confirmed CC0 1.0")
        if url.hostname != "upload.wikimedia.org":
            raise ValueError("Commons video must be hosted on official upload.wikimedia.org")
        if not url.path.startswith("/wikipedia/commons/"):
            raise ValueError("Commons uploaded video path not recognized")
        if not url.path.lower().endswith((".webm", ".ogv", ".mp4")):
            raise ValueError("Commons source is not a supported motion video")
        if not 300_000 <= int(item.get("file_size", 0)) <= MAX_BYTES:
            raise ValueError("Commons video file size is unknown or excessive")
        return sid
    if sid.startswith("mixkit-"):
        clip = sid.removeprefix("mixkit-")
        if (item.get("license") != MIXKIT_LICENSE
                or item.get("license_source_url") != MIXKIT_LICENSE_PAGE
                or url.hostname != "assets.mixkit.co"
                or url.path != "/videos/" + clip + "/" + clip + "-720.mp4"
                or url.query or url.fragment
                or not 5 <= float(item.get("duration", 0)) <= 180):
            raise ValueError("Mixkit Free clip must be individually verified; never scrape a library")
        return sid
    if item.get("license") != "Pexels License":
        raise ValueError("Pexels license not documented")
    if url.hostname == "www.pexels.com":
        if url.path != "/download/video/" + sid + "/":
            raise ValueError("Pexels download ID mismatch")
    elif url.hostname == "videos.pexels.com":
        if not url.path.startswith("/video-files/" + sid + "/") or not url.path.endswith(".mp4"):
            raise ValueError("Pexels CDN path mismatch")
    else:
        raise ValueError("Video download host not approved")
    return sid


def verified_mixkit(item, fetch=None):
    """One preselected asset only; recheck the official Free grant before use.

    This function does NOT search, enumerate, scrape, mass-download or
    automatically discover Mixkit assets. Mixkit terms prohibit mass bots.
    """
    sid=validated_media(item)
    if not sid.startswith("mixkit-"):
        raise ValueError("NOT_A_MIXKIT_FREE_CLIP")
    if fetch is None:
        req=urllib.request.Request(item["source_page"], headers={"User-Agent":UA})
        with urllib.request.urlopen(req,timeout=30) as response:
            if response.geturl()!=item["source_page"]:
                raise ValueError("MIXKIT_OFFICIAL_PAGE_REDIRECTED")
            html=response.read(250_000).decode("utf8",errors="replace")
    else:
        html=fetch(item["source_page"])
    clip=sid.removeprefix("mixkit-")
    if (not isinstance(html,str)
            or "Mixkit Stock Video Free License" not in html
            or "videoFree" not in html
            or "/videos/"+clip+"/"+clip+"-720.mp4" not in html):
        raise ValueError("MIXKIT_INDIVIDUAL_COMMERCIAL_FREE_LICENSE_NOT_RECONFIRMED")
    return sid


def commons_info(title):
    params = {
        "action": "query", "format": "json", "formatversion": "2",
        "titles": title, "prop": "imageinfo",
        "iiprop": "url|mime|size|sha1|extmetadata",
        "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Copyrighted|Artist|ImageDescription",
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=35) as response:
        data = json.load(response)
    pages = data.get("query", {}).get("pages", [])
    if len(pages) != 1 or pages[0].get("missing"):
        raise ValueError("Commons source page missing")
    info = (pages[0].get("imageinfo") or [{}])[0]
    return pages[0].get("title"), info


def verified_commons(item, fetch=commons_info):
    """Re-check license, content-address and remote asset before download."""
    sid = validated_media(item)
    if not sid.startswith("commons-"):
        raise ValueError("Not a Commons source")
    title = commons_file_title(item)
    official_title, info = fetch(title)
    meta = info.get("extmetadata") or {}
    lic = meta.get("LicenseShortName", {}).get("value", "")
    lic_url = meta.get("LicenseUrl", {}).get("value", "")
    if official_title != title:
        raise ValueError("Commons file redirected or renamed")
    if lic.strip().casefold() not in ("cc0", "cc0 1.0"):
        raise ValueError("CC0 license not confirmed by Commons API")
    if "creativecommons.org/publicdomain/zero/1.0" not in lic_url:
        raise ValueError("Unverified CC0 license URL")
    if not str(info.get("mime", "")).startswith("video/"):
        raise ValueError("Commons page no longer contains a video")
    if str(info.get("sha1", "")).lower() != item["commons_sha1"].lower():
        raise ValueError("Commons file content changed since editorial check")
    if int(info.get("size", 0)) != int(item.get("file_size", 0)):
        raise ValueError("Commons file size changed")
    expected = urllib.parse.urlsplit(item["url"])
    current = urllib.parse.urlsplit(info.get("url") or "")
    if (expected.scheme, expected.hostname, expected.path) != (
            current.scheme, current.hostname, current.path):
        raise ValueError("Commons video URL no longer matches original")
    return sid


def build_commons_candidate(title, info):
    """Convert an API item to an immutable, commercially reusable video record."""
    meta = info.get("extmetadata") or {}
    lic = meta.get("LicenseShortName", {}).get("value", "")
    lic_url = meta.get("LicenseUrl", {}).get("value", "")
    if lic.strip().casefold() not in ("cc0", "cc0 1.0"):
        return None
    if "creativecommons.org/publicdomain/zero/1.0" not in lic_url:
        return None
    if not str(info.get("mime", "")).startswith("video/"):
        return None
    if not 300_000 <= int(info.get("size") or 0) <= MAX_BYTES:
        return None
    file_sha1 = str(info.get("sha1", "")).lower()
    if not COMMONS_SHA1.fullmatch(file_sha1):
        return None
    author_raw = unescape(re.sub(r"<[^>]+>", " ", meta.get("Artist", {}).get("value", "")))
    author = re.sub(r"\s+", " ", author_raw).strip()[:100]
    if len(author) < 3 or "unknown" in author.casefold():
        return None
    info_url = info.get("url") or ""
    page = "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe=":_-()")
    item = {
        "key": "commons_" + file_sha1[:14], "source_page": page,
        "url": info_url, "author": author, "license": "CC0 1.0",
        "commons_sha1": file_sha1, "file_size": int(info["size"]),
        "source_title": title,
    }
    try:
        validated_media(item)
    except (TypeError, ValueError):
        return None
    return item
