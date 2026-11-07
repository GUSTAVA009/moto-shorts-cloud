"""Produce engaging, source-grounded Russian Shorts drafts without an LLM key.

A provider video *filename* only provides preflight evidence. It is never
proof that an action occurs in the actual frames: public release still needs
download/license checks, original GUSTAVA DEEP, ASR and exact MP4 visual review.
No fabricated incidents, shared characters, source tags or safety instructions.
"""
from __future__ import annotations
import hashlib
import os
import re
from urllib.parse import unquote, urlsplit

# Ordered from specific to generic. Recognize ACTIONS only from the provider's
# official file page URL, never our editorial profile or custom topic tags.
SCENES = (
    ("oil_change", r"(?:mechanic).*?(?:pouring|changing).*?(?:oil)|(?:oil).*?(?:engine|motorcycle)",
     "при замене масла", "механик меняет масло в мотоцикле", "замена масла",
     r"масл|мастер|двигател"),
    ("approach", r"(?:biker|rider).*?(?:walking|approach).*?(?:motorcycle|motorbike)",
     "перед поездкой", "байкер подходит к мотоциклу", "подход к мотоциклу",
     r"подход|байкер|перед старт"),
    ("helmet", r"(?:putting on|putting his|putting her).*?helmet",
     "перед стартом", "райдер надевает мотошлем", "надевание шлема",
     r"шлем|надева"),
    ("wheel", r"(?:repair|fix|replac|chang|servic|maintain).*?(?:tire|tyre|wheel)|(?:tire|tyre|wheel).*?(?:repair|replac|servic|maintain)",
     "при ремонте колеса", "мастер ремонтирует колесо байка", "ремонт колеса",
     r"колес|шин|покрыш"),
    ("inflation", r"(?:(?:pumping|pump|inflat).*?(?:motorcycle|motorbike).*?(?:tire|tyre)|(?:motorcycle|motorbike).*?(?:tire|tyre).*?(?:pump|inflat))",
     "при подкачке шины", "мастер накачивает шину мотоцикла", "подкачка шины",
     r"накач|шину|шин|насос"),
    ("motor", r"(?:engine|\bmotor\b).*?(?:repair|assembl|maintain|servic|restor)|(?:repair|assembl|maintain|servic|restor).*?(?:engine|\bmotor\b)",
     "при работе с двигателем", "механик занимается мотором мотоцикла", "работа с мотором",
     r"двигател|мотор"),
    ("jump", r"(?:motorcycle|motorbike|motocross|dirt bike).*?(?:jump|leap)|(?:jump|leap).*?(?:motorcycle|motorbike|motocross|dirt bike)",
     "на трамплине", "райдер прыгает с трамплина", "мотопрыжок",
     r"прыж|трамплин|взлета"),
    ("stunt", r"(?:(?:motorcycle|motorbike).*?(?:stunts?|wheelies?)|(?:stunts?|wheelies?).*?(?:motorcycle|motorbike))",
     "при выполнении трюка", "райдер выполняет трюк на мотоцикле", "мототрюк",
     r"трюк|стант"),
    ("mud", r"(?:motorcycle|motorbike|motocross|dirt bike).*?(?:mud|muddy)|(?:mud|muddy).*?(?:motorcycle|motorbike|motocross|dirt bike)",
     "в грязной колее", "райдер проезжает грязный участок", "грязевая трасса",
     r"гряз|коле"),
    ("snow", r"(?:motorcycle|motorbike|motocross|dirt bike).*?(?:snow|winter)|(?:snow|winter).*?(?:motorcycle|motorbike|motocross|dirt bike)",
     "на снегу", "мотоциклист едет по заснеженной дороге", "снег",
     r"снег|снеж|зим"),
    ("sand", r"(?:motorcycle|motorbike|motocross|dirt bike).*?(?:sand|desert|dune)|(?:sand|desert|dune).*?(?:motorcycle|motorbike|motocross|dirt bike)",
     "на песке", "райдер едет по песчаной трассе", "песчаная трасса",
     r"пес|дюн|пустын"),
    ("touring", r"(?:motorcycle|motorbike|touring bike|adventure bike).*?(?:touring|road trip|roadtrip|travel|journey)|(?:touring|road trip|roadtrip|travel|journey).*?(?:motorcycle|motorbike|touring bike|adventure bike)",
     "в путешествии", "райдер едет на туристическом мотоцикле", "мотопутешествие",
     r"турист|путешеств|маршрут|дальн"),
    ("race", r"(?:motorcycle|motorbike|motocross|dirt bike).*?(?:rac|championship|competition)|(?:rac|championship|competition).*?(?:motorcycle|motorbike|motocross|dirt bike)",
     "на гоночной трассе", "мотоциклист едет по треку", "поездка по треку",
     r"гонк|соревнован|старт|трек|трасс"),
    ("city", r"(?:motorcycl(?:e|es|ist|ists)|motorbike(?:s)?|scooter(?:s)?).*?(?:urban|city|traffic|street)|(?:urban|city|traffic|street).*?(?:motorcycl(?:e|es|ist|ists)|motorbike(?:s)?|scooter(?:s)?)",
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
    ("rain", r"motorcycle.*?(?:rain|wet)|(?:rain|wet).*?motorcycle",
     "под дождём", "байкер едет под дождём", "дождевая поездка",
     r"дожд|мокр|ливн"),
    ("ride", r"(?:motorcycle|motorbike|motocross|dirt bike).*?(?:riding|ride|travel|driving)|(?:riding|ride|travel|driving).*?(?:motorcycle|motorbike|motocross|dirt bike)",
     "на дороге", "байкер едет на мотоцикле", "поездка",
     r"едет|езд|поездк|движен"),
)


def scene_for(media):
    url = urlsplit(str(media.get("source_page") or ""))
    if url.hostname == "84-252-66-87.sslip.io":
        from moto_assets import validated_media
        # Action label is a preview hint only: the REAL MP4's actual six
        # frames are later checked independently by the Qwen Vision reviewer.
        validated_media(media)
        kind = {"riding":"ride"}.get(media.get("scene_action"),
                                    media.get("scene_action"))
        return next((s for s in SCENES if s[0]==kind),None)
    if url.scheme != "https" or url.hostname not in ("www.pexels.com", "commons.wikimedia.org", "mixkit.co"):
        return None
    # Some Pexels pages are named "riding on a hill" even though THREE
    # SHA-bound real source frames confirm a motorcycle airborne. Trust only
    # the approved original-pixel visual evidence, never self-assigned tags.
    if url.hostname == "www.pexels.com":
        from source_action_evidence import load_evidence, source_dynamic_action_verified
        if source_dynamic_action_verified(media):
            sid=str(media.get("url") or "").rstrip("/").split("/")[-1]
            evidence=load_evidence().get(sid)
            if evidence and evidence.get("action") == "stunt_jump":
                return next(x for x in SCENES if x[0] == "jump")
    # This exact Pexels 4K file was inspected at 0.4s, 2.6s, 3.3s,
    # 4.0s and 5.5s: an airborne motorcycle/backflip is visibly present.
    # Generic source pages saying "stunts" are NOT otherwise presumed jumps.
    if (url.hostname == "www.pexels.com"
            and url.path == "/video/dynamic-motocross-stunts-at-melbourne-show-34110751/"
            and media.get("url") == "https://www.pexels.com/download/video/34110751/"
            and media.get("author") == "Joolsmagools"
            and media.get("license") == "Pexels License"):
        return next(x for x in SCENES if x[0] == "jump")
    name = unquote(url.path).casefold().replace("-", " ").replace("_", " ")
    for scene in SCENES:
        if re.search(scene[1], name):
            return scene
    # Official page naming does not always match the historical category
    # regex. Only SHA-pinned three-frame evidence may qualify such a clip
    # as a riding scene. This is a planning hint; the final real-MP4
    # reviewer still has to verify moving motorcycle pixels.
    if url.hostname == "www.pexels.com":
        from source_action_evidence import load_evidence, source_dynamic_action_verified
        if source_dynamic_action_verified(media):
            sid=str(media.get("url") or "").rstrip("/").split("/")[-1]
            report=load_evidence().get(sid) or {}
            if report.get("action")=="riding":
                return next((x for x in SCENES if x[0]=="ride"),None)
    return None


def same_owner_original_pair(first, second):
    """Two independent owner-original MP4s: rights, SHA and actions must match.

    An earlier artificial SAME-BATCH restriction discarded a usable riding
    shot if its companion jump shot failed generation: the next genuinely
    owned jump could never pair with it. The two shots are separate events,
    not a claim of filming the same event or using two stock filmmakers.
    Actual actions remain subject to independent real-frame editorial QA.
    """
    from moto_assets import source_id, validated_media
    return (source_id(first).startswith("gustava-original-")
            and source_id(second).startswith("gustava-original-")
            and source_id(first) != source_id(second)
            and first.get("scene_action") != second.get("scene_action")
            and validated_media(first) == source_id(first)
            and validated_media(second) == source_id(second))


def pair_permitted(first, second):
    from moto_assets import source_id
    original_a = source_id(first).startswith("gustava-original-")
    original_b = source_id(second).startswith("gustava-original-")
    if original_a or original_b:
        return original_a and original_b and same_owner_original_pair(first,second)
    return first["author"].strip().casefold() != second["author"].strip().casefold()


def select_pair(sources, used_ids):
    """Prefer two distinct actions, independent creators or new owner-generated batch."""
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
    # A major source of 0/10 Buffer stock was otherwise technically valid
    # videos of an isolated tire/bolt/helmet. The actual six-frame reviewer
    # correctly rejected them because no motorcycle was visible in chapter 2.
    # When actual, owner-generated moving-motorcycle sources are available,
    # choose TWO of those first. All source SHA, ownership and independent
    # action checks remain mandatory. Pexels-only unit tests retain their
    # established sorting and license behavior.
    # Verified failed final MP4s: 'rain' often showed a car instead of a
    # bike; 'mountain' was a motionless distant object. Those scene labels
    # alone cannot fill a positive moving-motorcycle preflight.
    # They remain usable only after normal strict final-frame verification.
    fully_visible_owner_actions = {
        "ride", "jump", "mud", "city", "forest",
    }
    for index, (first, a) in enumerate(eligible):
        if (first.get("license") != "LTX OpenRAIL-M"
                or a[0] not in fully_visible_owner_actions):
            continue
        for second, b in eligible[index + 1:]:
            if (second.get("license") == "LTX OpenRAIL-M"
                    and b[0] in fully_visible_owner_actions
                    and a[0] != b[0]
                    and pair_permitted(first, second)):
                return [first, second]
    # Prefer a journey + track pairing; source title alone never proves an
    # organized race or multiple competitors are visible in the frames.
    for index, (first, a) in enumerate(eligible):
        for second, b in eligible[index + 1:]:
            if ({a[0], b[0]} == {"touring", "race"} and
                    pair_permitted(first, second)):
                return [first, second]
    for index, (first, a) in enumerate(eligible):
        for second, b in eligible[index + 1:]:
            if (a[0] != b[0] and pair_permitted(first,second)):
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


def touring_track_myth(sources, previous_titles, rewrite_attempt=0, previous_narrations=()):
    """Original ironic stereotype-rebuttal, never a claimed single event.

    Owner reference: YouTube Short A80XBI_rnb0 (only title and public
    description verified; do not reproduce uninspected video or music).
    """
    if len(sources) != 2:
        raise ValueError("MYTH_REQUIRES_TWO_REAL_SCENES")
    a, b = (scene_for(source) for source in sources)
    if a is None or b is None or {a[0], b[0]} != {"touring", "race"}:
        raise ValueError("MYTH_REQUIRES_TOURING_AND_RACING")
    token = "|".join(str(x["source_page"]) for x in sources)
    variant = hashlib.sha256(token.encode("utf8")).digest()[0] % 3
    openers = (
        "Мотоцикл для путешествий — скука? Так шутят диванные эксперты.",
        "Мотоцикл в путешествии — якобы без драйва? Диванный миф дня.",
        "Мотоцикл на дальнем маршруте скучнее гонки? Спорный стереотип.",
    )
    endings = (
        "А ты выбрал бы путешествие или гоночный трек?",
        "Что важнее лично тебе: горный маршрут или трек?",
        "Что тебе ближе: путешествие или трек?",
    )
    # The Qwen3 cloud narrator may require ~12-15 s for 125-160 chars.
    # Two actual moving shots in v3 are limited to 8 s each; lengthy
    # narration cannot be solved by looping licensed footage.
    narration_options = (
        f"Мотоцикл в путешествии скучный? {a[3].capitalize()}. "
        f"На другом видео {b[3]}. Разные люди и съёмки. Что ближе тебе?",
        f"Мотоцикл и разные дороги: {a[3]}. В другом сюжете {b[3]}. "
        f"Разные райдеры, не одна гонка. Что тебе интереснее?",
        f"Мотоцикл для дальнего пути или трека? Сначала {a[3]}. "
        f"Вторая съёмка: {b[3]}. Никакого общего события. Что выберешь?",
    )
    options = [n for n in narration_options if 125 <= len(n) <= 160]
    if not options:
        raise ValueError("MYTH_NARRATION_EXCEEDS_TWO_REAL_SCENE_CAPACITY")
    # Only select truly unused voice lines, without weakening QA or faking
    # stock diversity. If this action pair is exhausted, another pair is needed.
    used_narrations = {" ".join(str(n).casefold().split()) for n in previous_narrations}
    options = [n for n in options if " ".join(n.casefold().split()) not in used_narrations]
    if not options:
        raise ValueError("MYTH_NARRATIONS_EXHAUSTED")
    narration = options[rewrite_attempt % len(options)]
    titles = (
        "Туристический байк скучный? Проверь стереотип #shorts",
        "Миф о туристических мотоциклах: дорога против трека #shorts",
        "Путешествие или трек? Два мира мотоциклов #shorts",
    )
    item = {
        "title": titles[(variant + rewrite_attempt) % len(titles)], "narration": narration,
        "description": (
            "Ироничный разбор мифа о туристических байках. "
            "Два независимых лицензированных эпизода: путешествие и поездка по треку. "
            "Не одно событие и не сравнение характеристик моделей.\n\n#shorts"
        ),
        "caption_start": "МИФ: ТУРИСТ — ЭТО СКУЧНО?",
        "caption_middle": "ДОРОГА ИЛИ ГОНОЧНЫЙ ТРЕК?",
        "caption_end": "А ТЫ ЧТО ВЫБЕРЕШЬ?",
        "_editorial_format": "ironic_touring_vs_track_myth",
        "_creative_treatment": "myth_vs_reality_irony",
        "_generation_source": "keyless_original_touring_track_satire_v1",
    }
    require_filmable(item, sources)
    if item["title"].casefold() in {str(t).strip().casefold() for t in previous_titles}:
        raise ValueError("MYTH_TITLE_PREVIOUSLY_USED")
    return item

def grounded_riding_jump_story(sources, previous_titles,
                              rewrite_attempt=0, previous_narrations=()):
    """Technical observation grounded in independently reviewed real actions.

    Avoid the rejected generic 'A or B' contest. Ground each spoken claim
    in two real SHA-pinned motorcycle scenes; no landing footage is invented.
    """
    from source_action_evidence import source_dynamic_action_verified
    from moto_assets import source_id
    a,b=(scene_for(x) for x in sources)
    if (a is None or b is None or (a[0],b[0])!=("ride","jump")
            or not all(source_dynamic_action_verified(x) for x in sources)):
        raise ValueError("GROUNDING_REQUIRES_VERIFIED_RIDE_THEN_AIRBORNE_JUMP")
    options=[
        "Мотоцикл едет по дороге. Это первый кадр. Во втором кадре мотоциклист прыгает с трамплина. Теперь мотоцикл летит по воздуху. Перед нами настоящий прыжок на мотоцикле.",
        "Сначала байк едет по дороге. На другой записи райдер прыгает с трамплина. В воздухе колёса оторваны от земли. Посмотри, как меняется положение мотоцикла!",
    ]
    already={" ".join(str(x).casefold().split()) for x in previous_narrations}
    available=[x for x in options if " ".join(x.casefold().split()) not in already]
    if not available:
        raise ValueError("GROUNDING_RIDE_JUMP_NARRATION_EXHAUSTED")
    narration=available[rewrite_attempt % len(available)]
    titles=[
        "Оба колеса в воздухе: настоящий мотопрыжок #shorts",
        "Колёса оторваны от земли: мотопрыжок в деталях #shorts",
    ]
    titles=[x for x in titles if x.casefold() not in
            {str(y).casefold() for y in previous_titles}]
    if not titles:
        raise ValueError("GROUNDING_RIDE_JUMP_TITLE_EXHAUSTED")
    result={
        "title":titles[rewrite_attempt % len(titles)],
        "narration":narration,
        "description":(
            "Два независимых лицензированных видео: движение на дороге "
            "и настоящий прыжок мотоцикла над трамплином. "
            "Без выдуманных приземлений или общего заезда.\n\n#shorts"),
        "caption_start":"КОЛЁСА НА ДОРОГЕ",
        "caption_middle":"МОТОЦИКЛ В ВОЗДУХЕ",
        "caption_end":"ТРАЕКТОРИЯ РЕШАЕТ",
        "_editorial_format":"original_action_microguide_v1",
        "_creative_treatment":"observable_riding_jump_mechanics",
        "_generation_source":"keyless_sha_grounded_airborne_moto_v1",
    }
    require_filmable(result,sources)
    return result


def compose(sources, previous_titles, rewrite_attempt=0, previous_narrations=()):
    """A short, grounded contrast, not a fabricated one-event storyline."""
    if len(sources) != 2:
        raise ValueError("TWO_DISTINCT_LICENSED_ACTIONS_REQUIRED")
    a, b = (scene_for(s) for s in sources)
    if a is None or b is None or a[0] == b[0]:
        raise ValueError("NO_ACTION_DIVERSITY: source footage not suitable for story")
    if ((a[0],b[0]) == ("ride","jump")
            and os.environ.get("GUSTAVA_SOURCE_ACTION_EVIDENCE_REQUIRED")=="1"):
        return grounded_riding_jump_story(
            sources,previous_titles,rewrite_attempt,previous_narrations)
    if {a[0], b[0]} == {"touring", "race"}:
        return touring_track_myth(sources, previous_titles,
                                  rewrite_attempt=rewrite_attempt,
                                  previous_narrations=previous_narrations)
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
    concise_options = (
        f"Мотоцикл в двух сценах: {a[3]}. На другом видео {b[3]}. "
        f"Это независимые съёмки. Что ближе тебе?",
        f"Мотоцикл в разных сюжетах: {a[3]}. На второй съёмке {b[3]}. "
        f"Это разные люди и кадры. Что сильнее цепляет?",
        f"Мотоцикл под разными углами: {a[3]}. В другом ролике {b[3]}. "
        f"Два отдельных момента. Какой пересмотрел бы ты?",
        f"Мотоцикл в двух независимых кадрах: {a[3]}. На втором видео {b[3]}. "
        f"Люди не связаны друг с другом. Что интереснее?",
        f"Два разных видео о мотоциклах: сначала {a[3]}. Затем {b[3]}. "
        f"Это разные участники и съёмки. Какой момент сильнее?",
        f"Мотоцикл в разных сюжетах: {a[3]}. На другой записи {b[3]}. "
        f"Общее событие здесь не показано. Что ближе тебе?",
        f"Мотоцикл в двух независимых сюжетах: сначала {a[3]}. "
        f"Во втором кадре {b[3]}. Разные люди и съёмки. Что тебе ближе?",
    )
    filmable_options = [text for text in concise_options
                        if 125 <= len(text) <= 160]
    if not filmable_options:
        raise ValueError("NO_CONCISE_TWO_SCENE_NARRATION")
    # The original 7 generic narrations were exhausted by a large licensed
    # footage catalog. New assets then failed every rewrite although their
    # actions and creators were distinct. Expand the grounded dramatic beats,
    # rather than lowering catalog uniqueness or skipping voice/visual QA.
    hooks = (
        "Мотоцикл меняет характер каждого кадра:",
        "Мотоцикл: две сцены, но разные задачи:",
        "Не всякая мотоистория про скорость:",
        "Мотоцикл: обрати внимание на действия:",
        "Два эпизода с байками без постановки:",
        "Мотоцикл в деле: заметь контраст:",
        "Мотоцикл здесь показывает две ситуации:",
        "Мотоцикл: смотри не на фон, а на езду:",
        "За каждым мотокадром своё действие:",
        "Мотоцикл бывает интересен по-разному:",
    )
    transitions = (
        "На первом видео", "В первом эпизоде", "Сначала",
    )
    connectors = (
        "А в другом кадре", "На другой записи", "Во втором эпизоде",
        "Совсем в другом месте", "А затем, в отдельной съёмке",
    )
    questions = (
        "Что захотелось пересмотреть?",
        "Где больше точности движения?",
        "Какой эпизод тебе ближе?",
        "Какой момент кажется интереснее?",
        "Какая сцена выглядит убедительнее?",
        "Какая часть больше цепляет внимание?",
        "Какое движение ты заметил первым?",
        "Что показалось самым сложным?",
    )
    clarifiers = (
        "Это разные съёмки.",
        "Это отдельные записи, не один заезд.",
        "Оба действия показаны в разных видео.",
        "Кадры сняты отдельно, а не подряд.",
        "Это два эпизода из разных съёмок.",
        "Каждый из этих кадров снят отдельно.",
        "Один эпизод не продолжает другой.",
        "Сцены независимы друг от друга.",
    )
    expanded = [
        f"{hook} {transition.lower()} {a[3]}. "
        f"{connector} {b[3]}. {clarifier} {question}"
        for hook in hooks for transition in transitions
        for connector in connectors for clarifier in clarifiers
        for question in questions
    ]
    expanded = [t for t in expanded if 125 <= len(t) <= 160]
    filmable_options += expanded
    # Longer phrasing can be filtered out for brief action labels.
    # Build naturally short, still grounded utterances to sustain new videos
    # instead of cycling the same 7 narration strings.
    compact_hooks = (
        "Мотоцикл в двух кадрах:", "Мотоцикл и разные задачи:",
        "Мотоцикл — два момента:", "Мотоцикл и разные сцены:",
        "Мотоцикл в действии:", "Мотоцикл с двух сторон:",
        "Мотоцикл — смотри на детали:", "Мотоцикл и два эпизода:",
        "Мотоцикл: совсем разные ситуации:", "Мотоцикл — разные движения:",
        "Мотоцикл — не одна история:", "Мотоцикл и смена обстановки:",
    )
    compact_first = ("сначала", "в первой съёмке", "на одном видео",
                     "в первом эпизоде", "вначале")
    compact_second = ("далее", "а отдельно", "во втором видео",
                      "на другой записи", "затем отдельно")
    compact_notes = (
        "Это не один заезд.", "Видео сняты отдельно.",
        "Съёмки не связаны.", "Эпизоды разные.",
        "Это разные моменты.", "Один кадр не продолжает другой.",
        "Здесь две независимые записи.",
    )
    compact_ends = (
        "Что зацепило?", "Что запомнил?", "Что интереснее?",
        "Где больше динамики?", "Куда бы посмотрел?",
        "Что захотелось пересмотреть?", "На что обратил внимание?",
    )
    filmable_options += [
        f"{hook} {first} {a[3]}, {second} {b[3]}. {note} {ending}"
        for hook in compact_hooks for first in compact_first
        for second in compact_second for note in compact_notes
        for ending in compact_ends
        if 125 <= len(f"{hook} {first} {a[3]}, {second} {b[3]}. {note} {ending}") <= 160
    ]
    if not filmable_options:
        raise ValueError("NO_GROUNDED_NARRATION_VARIANTS")
    # Vary by catalog position and rewrite attempt. All expressions still
    # describe exactly the two evidenced actions; no fictional incident.
    # After many production batches the modulo formula began choosing an
    # already-used script for 3 retries. Select an unused candidate instead.
    # Preserve the permanent dedup/filmability checks downstream.
    used_narrations = {" ".join(str(n).casefold().split()) for n in previous_narrations}
    start = ((variant * 3 + len(previous_titles) * 17 + rewrite_attempt * 37)
             % len(filmable_options))
    narration = next(
        (candidate for offset in range(len(filmable_options))
         for candidate in [filmable_options[(start + offset) % len(filmable_options)]]
         if " ".join(candidate.casefold().split()) not in used_narrations),
        None)
    if narration is None:
        raise ValueError("SOURCE_STORY_NARRATIONS_EXHAUSTED")
    # Earlier versions generated exactly ONE title for every action pair.
    # On 2026-11-02 real refill 41410904531 rejected fresh, licensed
    # footage three times with SOURCE_STORY_TITLE_ALREADY_USED because the
    # title was reused independently of the clips. Offer concise distinct
    # *source-grounded* hooks without claiming two clips show one event.
    title_options = (
        f"{a[4].capitalize()} или {b[4]}: какой момент интереснее? #shorts",
        f"{a[4].capitalize()} и {b[4]} — какой кадр сильнее? #shorts",
        f"Два мотоэпизода: {a[4]} и {b[4]}. Что выберешь? #shorts",
        f"Что больше цепляет: {a[4]} или {b[4]}? #shorts",
        f"Два разных райдера: {a[4]} и {b[4]}. Твой выбор? #shorts",
        f"{a[4].capitalize()} / {b[4]} — две разные мотосцены #shorts",
        f"Мото на деле: {a[4]} и {b[4]}. Где больше драйва? #shorts",
    )
    # Additional action-specific titles break the seven-title ceiling. A
    # distinct title is still never permission to reuse footage or narration.
    title_options += (
        f"От {a[4]} до {b[4]} — две мотосцены #shorts",
        f"{a[4].capitalize()} против {b[4]}: две разные задачи #shorts",
        f"Что меняется между {a[4]} и {b[4]}? #shorts",
        f"Неожиданный контраст: {a[4]} и {b[4]} #shorts",
        f"Мотокадры из разных условий: {a[4]} и {b[4]} #shorts",
        f"Внимание к деталям: {a[4]} и {b[4]} #shorts",
        f"Не одинаковая езда: {a[4]} и {b[4]} #shorts",
        f"{a[4].capitalize()}, потом {b[4]} — разные действия #shorts",
        f"Две стороны мото: {a[4]} и {b[4]} #shorts",
        f"Один байк? Нет: {a[4]} и {b[4]} #shorts",
        f"{a[4].capitalize()} и {b[4]}: реальные движения #shorts",
        f"Разные условия, разная езда: {a[4]} и {b[4]} #shorts",
        f"Два эпизода, две задачи: {a[4]} / {b[4]} #shorts",
        f"Погляди на действия: {a[4]} и {b[4]} #shorts",
        f"Разные дороги: {a[4]} и {b[4]} #shorts",
        f"Мотоциклы в движении: {a[4]} и {b[4]} #shorts",
    )
    used = {str(old).strip().casefold() for old in previous_titles}
    title = next((option for offset in range(len(title_options))
                  for option in (title_options[(variant+rewrite_attempt+offset)%len(title_options)],)
                  if option.casefold() not in used and len(option)<=100), None)
    if title is None:
        raise ValueError("SOURCE_STORY_ALL_GROUNDED_TITLES_ALREADY_USED")
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
    if title.casefold() in used:
        raise ValueError("SOURCE_STORY_TITLE_ALREADY_USED")
    if len(title) > 100:
        raise ValueError("TITLE_TOO_LONG")
    return prose
