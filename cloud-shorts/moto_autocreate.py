#!/usr/bin/env python3
"""Sustain an ORIGINAL motorcycle Shorts queue using licensed source APIs + AI.

Pexels (optional PEXELS_API_KEY) and Wikimedia Commons CC0 (keyless) are
independent media providers. A user-provided OpenAI/OpenRouter API key is
required for independently composed, context-aware Russian scripts; no
headline is converted into a false incident and stock clips are never reused.

If credentials or rights-cleared footage are unavailable, return an explicit
supply blocker. Never forge licensing or silently fabricate a new video.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request

from editorial_guard import validate_catalog, source_id
from moto_assets import validated_media, build_commons_candidate
from render_episode import validate_episode
from engagement_cta import CTA_KINDS
from autofill_catalog import github

ROOT = Path(__file__).resolve().parent
CATALOG = "cloud-shorts/episodes.json"

# Five genuinely different settings, bike types and creative angles. The model
# writes the original STORY about those actual subject-matter constraints.
THEMES = (
    ("forest", "motorcycle forest trail", "forest-trail", "forest-trailbike",
     "woods-rider", "forest-path-and-riding"),
    ("motocross", "motocross race dirt bikes", "race-track", "motocross-bike",
     "track-racers", "rider-at-prepared-track"),
    ("repair", "motorcycle mechanic garage repair", "garage-workshop", "workshop-bike",
     "garage-mechanics", "mechanic-bike-servicing"),
    ("mountain", "motorcycle mountain road adventure", "rocky-mountain-road", "adventure-tourer",
     "mountain-travelers", "mountain-journey"),
    ("rain", "motorcycle riding rain road", "wet-asphalt-road", "street-motorbike",
     "road-commuters", "rainy-motorcycle-road"),
    ("desert", "dirt bike desert offroad", "desert-trail", "sand-motorcycle",
     "desert-riders", "sand-terrain"),
    ("city", "motorcycles in city traffic", "urban-streets", "urban-motorbike",
     "city-riders", "urban-riding"),
    ("vintage", "classic motorcycle restoration", "vintage-workshop", "classic-motorcycle",
     "classic-restorers", "vintage-bike-work"),
    ("roadtrip", "motorbike country road travel", "countryside-road", "touring-motorcycle",
     "touring-travelers", "scenic-country-road"),
    ("training", "motorcycle training closed track", "practice-circuit", "training-motorcycle",
     "track-learners", "closed-course-practice"),
    ("helmet", "motorcycle helmet protective gear", "riding-gear-workshop", "motorbike-safety-gear",
     "gear-specialists", "helmet-gear-choice"),
    ("dirt", "dirt bike on muddy trail", "muddy-trail-road", "offroad-dirtbike",
     "trail-groups", "muddy-terrain"),
    ("sunset", "motorcycle scenic sunset", "sunset-road", "travel-motorbike",
     "evening-riders", "sunset-journey"),
    ("snow", "motorcycle riding in snow winter", "snow-trail", "winter-offroad-moto",
     "winter-riders", "snow-covered-path"),
    ("racing", "motorcycle racing circuit riders", "race-paddock", "track-racing-bike",
     "racing-crews", "circuit-racing"),
)

CTA_CYCLE = [
    ("comment", "НАПИШИ СВОЙ ВЫБОР", "Расскажи в комментариях, какой маршрут выбрал бы ты."),
    ("subscribe", "ПОДПИШИСЬ НА МОТОИСТОРИИ", "Подпишись, если любишь настоящие мотопутешествия."),
    ("share", "ОТПРАВЬ ДРУГУ С МОТО", "Поделись роликом с другом, который любит мотоциклы."),
    ("like", "НРАВИТСЯ МОТО? ЛАЙК!", "Поставь лайк, если тебе нравится эта мототема."),
]

MOTO_SIGNALS = re.compile(
    r"(motorcycl|motorbike|motocross|motocross|moto[-_ ]|dirt[-_ ]bike|"
    r"motor[-_ ]racing|supermoto|enduro|two[-_ ]wheeler)", re.I)
BANNED_CONTEXT = re.compile(r"\b(naked bike ride|shooting|killed|dead|fatal|suicide|stunt crash)\b", re.I)


def http_json(url, headers=None, payload=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": "GUSTAVA-Enduro-Editorial/1.0",
        **(headers or {}),
    }, data=json.dumps(payload).encode("utf8") if payload is not None else None)
    with urllib.request.urlopen(req, timeout=35) as response:
        return json.load(response)


def pexels_results(theme, page, api_key, fetch=http_json):
    if not api_key:
        return []
    params = urllib.parse.urlencode({"query": theme[1], "per_page": 80,
                                     "page": page, "orientation": "portrait"})
    url = "https://api.pexels.com/v1/videos/search?" + params
    body = fetch(url, {"Authorization": api_key})
    found = []
    for video in body.get("videos", []):
        raw_id = video.get("id")
        if not str(raw_id).isdigit():
            continue
        page_url = urllib.parse.urlsplit(str(video.get("url") or ""))
        if page_url.scheme != "https" or page_url.hostname != "www.pexels.com":
            continue
        if not page_url.path.startswith("/video/") or not page_url.path.rstrip("/").endswith("-" + str(raw_id)):
            continue
        phrase = urllib.parse.unquote(page_url.path).lower()
        if not MOTO_SIGNALS.search(phrase) or BANNED_CONTEXT.search(phrase):
            continue
        duration = int(video.get("duration") or 0)
        if not 9 <= duration <= 180:
            continue
        creator = str((video.get("user") or {}).get("name") or "").strip()[:80]
        if len(creator) < 3:
            continue
        if not video.get("video_files"):
            continue
        record = {
            "key": "px_" + str(raw_id),
            "url": "https://www.pexels.com/download/video/" + str(raw_id) + "/",
            "source_page": urllib.parse.urlunsplit((page_url.scheme, page_url.netloc, page_url.path, "", "")),
            "author": creator, "license": "Pexels License", "duration": duration,
            "source_title": phrase.split("/video/")[-1].strip("/").replace("-", " ")[:110],
        }
        validated_media(record)
        found.append(record)
    return found


def commons_results(theme, fetch=http_json):
    params = urllib.parse.urlencode({
        "action":"query", "format":"json", "formatversion":"2",
        "generator":"search", "gsrsearch": theme[1] + " filetype:video",
        "gsrnamespace":6, "gsrlimit":50, "prop":"imageinfo",
        "iiprop":"url|mime|size|sha1|extmetadata",
        "iiextmetadatafilter":"LicenseShortName|LicenseUrl|Copyrighted|Artist",
    })
    data = fetch("https://commons.wikimedia.org/w/api.php?" + params)
    rows = []
    for page in data.get("query", {}).get("pages", []):
        title = page.get("title") or ""
        if not MOTO_SIGNALS.search(title) or BANNED_CONTEXT.search(title):
            continue
        info = (page.get("imageinfo") or [{}])[0]
        c = build_commons_candidate(title, info)
        if c:
            rows.append(c)
    return rows


def choose_sources(candidates, used_ids, n=3):
    selected, creators, seen = [], set(), set()
    for src in candidates:
        key = source_id(src)
        who = src["author"].strip().casefold()
        if key in used_ids or key in seen or who in creators:
            continue
        validated_media(src)
        selected.append(src)
        creators.add(who)
        seen.add(key)
        if len(selected) == n:
            return selected
    return selected if len(selected) >= 2 else []


def choose_theme(existing):
    # Rotate subject, physical setting and cast. Do NOT reuse the previous
    # three concepts or the immediate predecessor's bike type.
    recent = [x["editorial"] for x in existing[-3:]]
    order = list(range(len(THEMES)))
    position = len(existing) % len(THEMES)
    order = order[position:] + order[:position]
    for ix in order:
        t = THEMES[ix]
        if any(t[2] == p.get("environment") or t[5] == p.get("story") for p in recent):
            continue
        if existing and t[3] == existing[-1]["editorial"].get("bike"):
            continue
        return t
    raise RuntimeError("No diverse motorcycle angles available: new editorial research needed")


def story_model_client():
    if os.getenv("OPENAI_API_KEY"):
        return ("https://api.openai.com/v1/chat/completions",
                os.environ["OPENAI_API_KEY"], os.getenv("GUSTAVA_SCRIPT_MODEL", "gpt-4.1-mini"))
    if os.getenv("OPENROUTER_API_KEY"):
        return ("https://openrouter.ai/api/v1/chat/completions",
                os.environ["OPENROUTER_API_KEY"],
                os.getenv("GUSTAVA_SCRIPT_MODEL", "openai/gpt-4o-mini"))
    return None


def original_story(theme, sources, previous_titles, client=None, fetch=http_json):
    provider = client if client is not None else story_model_client()
    if not provider:
        raise RuntimeError("ORIGINAL_SCRIPT_MODEL_MISSING: add OPENAI_API_KEY or OPENROUTER_API_KEY")
    endpoint, key, model = provider
    topics = [{"source_title": x.get("source_title", ""), "creator": x["author"]}
              for x in sources]
    instruction = (
        "Напиши ОДИН оригинальный русскоязычный сценарий для GUSTAVA Enduro Shorts. "
        "Строго мототема, 18-25 секунд. Описания файлов лишь контекст, не доказательство "
        "того, что событие действительно произошло. Это НЕ одна история с общими героями: "
        "показаны независимые клипы. Никаких вымышленных аварий, дат, имён, рекордов, "
        "травм, неподтверждённых технических фактов и опасных инструкций. "
        "Не используй слова хапыч, эндуро в публичном тексте, не используй ссылки. "
        "Это новое информативное наблюдение, интересная реальная мотоидея и один "
        "естественный вопрос, а не кликбейт, реклама или пять одинаковых общих советов. "
        "Не копируй предшествующие заголовки. Верни только JSON с ключами: "
        "title, narration, description, caption_start, caption_middle, caption_end. "
        "Title <= 100 символов, narration 125-300 символов, по-русски, "
        "первое предложение содержит слово мотоцикл/байк/мотокросс; "
        "подписи <= 31 символ. Добавь #shorts в заголовок и описание.")
    data = {
        "model": model, "temperature": .9, "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": json.dumps({
                "creative_pillar": theme[0], "search_situation": theme[1],
                "independent_licensed_video_contexts": topics,
                "avoid_titles": previous_titles[-12:],
            }, ensure_ascii=False)},
        ],
        "max_tokens": 580,
    }
    result = fetch(endpoint, {"Authorization": "Bearer " + key,
                              "Content-Type": "application/json"}, data)
    response = ((result.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    obj = json.loads(response)
    required = ("title", "narration", "description", "caption_start",
                "caption_middle", "caption_end")
    if any(not isinstance(obj.get(k), str) or not obj[k].strip() for k in required):
        raise ValueError("AI story is not complete")
    if not 125 <= len(obj["narration"]) <= 300:
        raise ValueError("Generated narration exceeds reviewed length")
    if not re.search(r"мотоцик|мотокросс|байк", obj["narration"], re.I):
        raise ValueError("AI story is not explicitly about motorcycles")
    if any(t in " ".join(obj.values()).casefold() for t in
           ("хапыч", "эндуро", "https://", "www.", "купи лайк", "накрут")):
        raise ValueError("AI output contains banned content or external links")
    if any(re.search(r"\b\d{2,}\b", str(x)) for x in obj.values()):
        raise ValueError("AI created unverified numerical claim")
    if len(obj["title"]) > 100 or any(len(obj[k]) > 31 for k in required[3:]):
        raise ValueError("Unusable Shorts caption/title size")
    return obj


def assemble_episode(catalog, theme, media, prose, seed_index):
    if len(media) < 2:
        raise ValueError("Two distinct licensed creators required")
    for src in media:
        validated_media(src)
    short_hash = hashlib.sha256(("|".join(source_id(x) for x in media) +
                                 prose["narration"]).encode("utf8")).hexdigest()[:12]
    slug = "moto-" + theme[0] + "-" + short_hash
    cta_kind, overlay, sentence = CTA_CYCLE[seed_index % len(CTA_CYCLE)]
    sources = [dict(x, key="clip_" + str(i)) for i, x in enumerate(media)]
    cuts = []
    for idx in range(12):
        source = sources[idx % len(sources)]
        duration = min(int(source.get("duration") or 14), 120)
        offset = (idx // len(sources)) * 2.15
        if offset >= duration - 2.2:
            offset = max(0.0, duration - 2.8)
        cuts.append({"source": source["key"], "start": round(offset, 2), "seconds": 2.15})
    ep = {
        "id": slug, "auto_preview": True, "auto_publish": True,
        "channel_niche": "motorcycle", "research_pillar": "motorcycle",
        "voice_engine": "kokoro_ru_dima",
        **{k: prose[k] for k in ("title", "narration", "description",
            "caption_start", "caption_middle", "caption_end")},
        "max_duration_seconds": 34, "opening_trim_seconds": 0.1,
        "music_style": ("race-breakbeat" if theme[0] in ("motocross", "racing")
                        else "garage-groove" if theme[0] in ("repair", "vintage")
                        else "night-drive" if theme[0] in ("city", "sunset")
                        else "action"),
        "music_bpm": 106 + (seed_index * 11) % 37,
        "footage": sources, "shots": cuts,
        "editorial": {
            "environment": theme[2] + "-" + short_hash[:5],
            "bike": theme[3],
            "people": theme[4] + "-" + short_hash[:5],
            "story": theme[5] + "-" + short_hash[:5],
            "visual": "three-clips-" + short_hash[:5],
        },
        "tags": ["мото", "мотокросс", "shorts"],
        "cta": {"kind": cta_kind, "overlay": overlay, "description": sentence},
        "source_selection": "Independent official video APIs, no clip reuse",
        "generation_provenance": "Original authoring by model from broad licensed scene context",
    }
    # Existing editorial uniqueness and Russian QA still apply independently.
    validate_episode(ep)
    validate_catalog({"episodes": catalog["episodes"] + [ep]})
    return ep


def create_one(catalog, source_fetch=pexels_results, commons_fetch=commons_results,
               prose_factory=original_story, permanently_used=()):
    # IDs from removed failed/revised footage are still reserved forever.
    used = set(permanently_used) | {
        source_id(x) for ep in catalog["episodes"] for x in ep["footage"]
    }
    themes = [choose_theme(catalog["episodes"])]
    # Every source must be independently rights-verified. Search multiple
    # results/pages, preferring explicitly motor-related original stock footage.
    theme = themes[0]
    found = []
    key = os.getenv("PEXELS_API_KEY", "")
    if key:
        for page in (1, 2, 3):
            found.extend(source_fetch(theme, page, key))
            if len(choose_sources(found, used)) >= 3:
                break
    if len(choose_sources(found, used)) < 2:
        found.extend(commons_fetch(theme))
    media = choose_sources(found, used)
    if len(media) < 2:
        raise RuntimeError("NO_NEW_LICENSED_MOTO_CLIPS: cannot invent footage")
    problem = None
    for attempt in range(3):
        try:
            prose = prose_factory(theme, media,
                                  [x["title"] for x in catalog["episodes"]])
            return assemble_episode(catalog, theme, media, prose,
                                    len(catalog["episodes"]))
        except (ValueError, KeyError, TypeError) as exc:
            # Do not lower originality or license checks. Boundedly request
            # a different independent script if its structure is invalid.
            problem = type(exc).__name__
            print("ORIGINAL_SCRIPT_QA_RETRY", attempt + 1, problem, flush=True)
    raise RuntimeError("ORIGINAL_SCRIPT_QA_FAILED_AFTER_3_TRIES: " + str(problem))


def main():
    from autofill_catalog import CATALOG_PATH
    import base64
    if not story_model_client():
        print("AUTOMATIC_STORY_SUPPLY_BLOCKED: OPENAI_API_KEY or OPENROUTER_API_KEY missing")
        return 2
    remote = github("GET", "contents/" + CATALOG_PATH + "?ref=main")
    catalog = json.loads(base64.b64decode(remote["content"]))
    selected = create_one(catalog)
    raw = json.dumps({"episodes": catalog["episodes"] + [selected]},
                     ensure_ascii=False, indent=2) + "\n"
    github("PUT", "contents/" + CATALOG_PATH, {
        "message": "Add new independent licensed motorcycle original " + selected["id"],
        "branch": "main", "sha": remote["sha"],
        "content": base64.b64encode(raw.encode("utf8")).decode("ascii"),
    })
    print("ORIGINAL_NEW_LICENSED_MOTORCYCLE_STORY_CREATED",
          selected["id"], len(selected["footage"]), "unique clips")
    if os.getenv("GITHUB_EVENT_NAME") != "schedule":
        github("POST", "actions/workflows/daily-preview.yml/dispatches", {"ref":"main"})
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError, KeyError, OSError) as error:
        print("ORIGINAL_STORY_SUPPLY_STOPPED", type(error).__name__,
              str(error)[:220], file=sys.stderr)
        raise SystemExit(1)
