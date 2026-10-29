#!/usr/bin/env python3
"""Read-only reconnaissance of copyright-clean Commons motorcycle video supply."""
import json
import urllib.parse
import urllib.request

UA = "GUSTAVA-Enduro-Content-Finder/1.0 (automated copyright-check; Wikimedia API)"
SEARCHES = [
    "motorcycle filetype:video",
    "motocross filetype:video",
    "motorbike filetype:video",
    "motorcycle racing filetype:video",
    "motorcycle ride filetype:video",
]
for term in SEARCHES:
    params = {
        "action": "query", "format": "json", "formatversion": "2",
        "generator": "search", "gsrsearch": term,
        "gsrnamespace": 6, "gsrlimit": 50,
        "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata",
        "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Copyrighted|Artist|ImageDescription",
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as h:
            data = json.load(h)
        results = []
        for row in data.get("query", {}).get("pages", []):
            info = (row.get("imageinfo") or [{}])[0]
            lic = info.get("extmetadata", {}).get("LicenseShortName", {}).get("value", "")
            mime = info.get("mime", "")
            if mime.startswith("video/"):
                results.append({"title":row.get("title"),"license":lic,"mime":mime,
                                "size":info.get("size"),"url":(info.get("url") or "")[:120]})
        print("COMMONS_RESEARCH", term, "video_results", len(results),
              json.dumps(results[:15], ensure_ascii=False), flush=True)
    except Exception as e:
        print("COMMONS_UNAVAILABLE", term, type(e).__name__, str(e)[:160], flush=True)
