"""Produce engaging, source-grounded Russian Shorts drafts without an LLM key.

A provider video *filename* only provides preflight evidence. It is never
proof that an action occurs in the actual frames: public release still needs
download/license checks, original GUSTAVA DEEP, ASR and exact MP4 visual review.
No fabricated incidents, shared characters, source tags or safety instructions.
"""
from __future__ import annotations
import hashlib
import re
from urllib.parse import unquote, urlsplit

# Ordered from specific to generic. Recognize ACTIONS only from the provider's
# official file page URL, never our editorial profile or custom topic tags.
SCENES = (
    ("helmet", r"(?:putting on|putting his|putting her).*?helmet",
     "перед стартом", "райдер надевает мотошлем", "надевание шлема",
     r"шлем|надева"),
    ("wheel", r"(?:repair|fix|replac|chang|servic|maintain).*?(?:tire|tyre|wheel)|(?:tire|tyre|wheel).*?(?:repair|replac|servic|maintain)",
     "при ремонте колеса", "мастер ремонтирует колесо байка", "ремонт колеса",
     r"колес|шин|покрыш"),
    ("motor", r"(?:engine|motor).*?(?:repair|assembl|maintain|servic|restor)|(?:repair|assembl|maintain|servic|restor).*?(?:engine|motor)",
     "при работе с двигателем", "механик занимается мотором мотоцикла", "работа с мотором",
     r"двигател|мотор"),
    ("jump", r"(?:motorcycle|motorbike|motocross|dirt bike).*?(?:jump|leap)|(?:jump|leap).*?(?:motorcycle|motorbike|motocross|dirt bike)",
     "на трамплине", "райдер прыгает с трамплина", "мотопрыжок",
     r"прыж|трамплин|взлета"),
    ("mud", r"(?:motorcycle|motorbike|motocross|dirt bike).*?(?:mud|muddy)|(?:mud|muddy).*?(?:motorcycle|motorbike|motocross|dirt bike)",
     "в грязной колее", "райдер проезжает грязный участок", "грязевая трасса",
     r"гряз|коле"),
    ("snow", r"(?:motorcycle|motorbike|motocross|dirt bike).*?(?:snow|winter)|(?:snow|winter).*?(?:motorcycle|motorbike|motocross|dirt bike)",
     "на снегу", "мотоциклист едет по заснеженной дороге", "снег",
     r"снег|зим"),
    ("sand", r"(?:motorcycle|motorbike|motocross|dirt bike).*?(?:sand|desert|dune)|(?:sand|desert|dune).*?(?:motorcycle|motorbike|motocross|dirt bike)",
     "на песке", "райдер едет по песчаной трассе", "песчаная трасса",
     r"пес|дюн|пустын"),
    ("race", r"(?:motorcycle|motorbike|motocross|dirt bike).*?(?:rac|championship|competition)|(?:rac|championship|competition).*?(?:motorcycle|motorbike|motocross|dirt bike)",
     "на гоночной трассе", "мотоциклисты участвуют в гонке", "мотогонка",
     r"гонк|соревнован|старт"),
    ("city", r"(?:motorcycle|motorbike|scooter).*?(?:urban|city|traffic|street)|(?:urban|city|traffic|street).*?(?:motorcycle|motorbike|scooter)",
     "в городском потоке", "байкер едет по городской улице", "городская поездка",
     r"город|улиц|поток"),
    ("forest", r"(?:motorcycle|motorbike|dirt bike).*?(?:forest|woods)|(?:forest|woods).*?(?:motorcycle|motorbike|dirt bike)",
     "на лесной тропе", "райдер едет через лес", "лесной заезд",
     r"лес|троп"),
    ("mountain", r"(?:motorcycle|motorbike|dirt bike).*?(?:mountain|cliff|highland)|(?:mountain|cliff|highland).*?(?:motorcycle|motorbike|dirt bike)",
     "в горах", "райдер едет по горной дороге", "горный маршрут",
     r"горн|серпантин|склон"),
    ("repair", r"(?:mechanic|repair|fixing|tinkering|servic|maintain).*?(?:motorcycle|motorbike|bike)|(?:motorcycle|motorbike).*?(?:mechanic|repair|fixing|tinkering|servic|maintain)",
     "в мастерской", "механик работает с мотоциклом", "ремонт байка",
     r"мастер|механик|ремонт"),
    ("ride", r"(?:motorcycle|motorbike|motocross|dirt bike).*?(?:riding|ride|travel|driving)|(?:riding|ride|travel|driving).*?(?:motorcycle|motorbike|motocross|dirt bike)",
     "на дороге", "байкер едет на мотоцикле", "поездка",
     r"едет|езд|поездк|движен"),
)


def scene_for(media):
    url = urlsplit(str(media.get("source_page") or ""))
    if url.scheme != "https" or url.hostname not in ("www.pexels.com", "commons.wikimedia.org"):
        return None
    name = unquote(url.path).casefold().replace("-", " ").replace("_", " ")
    for scene in SCENES:
        if re.search(scene[1], name):
            return scene
    return None


def select_pair(sources, used_ids):
    """Prefer two distinct *actions*, distinct creators, unconsumed real clips."""
    from moto_assets import source_id, validated_media
    eligible, seen = [], set()
    for media in sources:
        identity = source_id(media)
        if identity in used_ids or identity in seen:
            continue
        seen.add(identity)
        scene = scene_for(media)
        if scene is None:
            continue
        validated_media(media)
        eligible.append((media, scene))
    for index, (first, a) in enumerate(eligible):
        for second, b in eligible[index + 1:]:
            if (a[0] != b[0] and
                    first["author"].strip().casefold() != second["author"].strip().casefold()):
                return [first, second]
    return []


def require_filmable(prose, sources):
    if len(sources) != 2:
        raise ValueError("TWO_REAL_SCENES_REQUIRED")
    scenes = [scene_for(source) for source in sources]
    if any(scene is None for scene in scenes) or scenes[0][0] == scenes[1][0]:
        raise ValueError("SCENE_ACTION_EVIDENCE_MISSING")
    narration = str(prose.get("narration") or "").casefold()
    if not all(re.search(scene[5], narration) for scene in scenes):
        raise ValueError("UNRELATED_BORING_SCRIPT: narration does not describe both source actions")
    if not 125 <= len(narration) <= 300:
        raise ValueError("NARRATION_DURATION_UNSAFE")
    return [scene[0] for scene in scenes]


def compose(sources, previous_titles):
    """A short, grounded contrast, not a fabricated one-event storyline."""
    if len(sources) != 2:
        raise ValueError("TWO_DISTINCT_LICENSED_ACTIONS_REQUIRED")
    a, b = (scene_for(s) for s in sources)
    if a is None or b is None or a[0] == b[0]:
        raise ValueError("NO_ACTION_DIVERSITY: source footage not suitable for story")
    token = "|".join(str(s["source_page"]) for s in sources) + "|" + str(len(previous_titles))
    variant = hashlib.sha256(token.encode("utf8")).digest()[0] % 3
    openings = (
        f"Мотоцикл {a[2]} или {b[2]} — какой кадр цепляет сильнее?",
        f"Мотоцикл {a[2]}, а потом {b[2]}. Смотри, какая разница.",
        f"Мотоцикл {a[2]} и {b[2]}: это два разных испытания.",
    )
    ending = (
        f"Тебе ближе {a[4]} или {b[4]}?",
        f"Что ты пересмотрел бы: {a[4]} или {b[4]}?",
        f"Какой момент сильнее: {a[4]} или {b[4]}?",
    )
    narration = (f"{openings[variant]} Сначала {a[3]}. "
                 f"На другом, независимом видео {b[3]}. "
                 f"Это разные люди и съёмки, не один заезд. {ending[variant]}")
    title = f"{a[4].capitalize()} или {b[4]}: какой момент интереснее? #shorts"
    prose = {
        "title": title, "narration": narration,
        "description": (f"Две разные мотоистории: {a[4]} и {b[4]}. "
                        "Независимые кадры, без выдуманного общего события.\n\n#shorts"),
        "caption_start": a[4].upper()[:31],
        "caption_middle": b[4].upper()[:31],
        "caption_end": "ЧТО ВЫБРАЛ БЫ ТЫ?",
        "_editorial_format": "source_anchored_action_contrast",
        "_generation_source": "keyless_action_filmable_v1",
    }
    require_filmable(prose, sources)
    if title.casefold() in {str(t).casefold() for t in previous_titles}:
        raise ValueError("SOURCE_STORY_TITLE_ALREADY_USED")
    if len(title) > 100:
        raise ValueError("TITLE_TOO_LONG")
    return prose
