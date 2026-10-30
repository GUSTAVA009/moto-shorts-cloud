#!/usr/bin/env python3
"""150,000 addressable, keyless Russian motorcycle narration variants.

Variants are editorial combinations, NOT independently verified true events,
licensed footage, approved audio, or completed MP4s. Every episode must
separately pass the existing editorial, originality and production QA.
"""
from __future__ import annotations
import argparse
import hashlib
import json

VERSION = 2
THEMES = {
    "forest": ("Лесная тропа", "лесной маршрут", (
        "покрытие", "обзор", "колея", "повороты", "маршрут", "дистанция",
        "рельеф", "погода", "ориентиры", "подготовка")),
    "motocross": ("Мотокросс", "мотокросс", (
        "траектория", "грунт", "защита", "повороты", "разминка", "техника",
        "площадка", "ритм", "снаряжение", "разметка")),
    "repair": ("Мастерская", "работа в мастерской", (
        "шины", "инструмент", "крепёж", "цепь", "свет", "тормоза",
        "чистота", "осмотр", "порядок", "руководство")),
    "mountain": ("Горный маршрут", "горная дорога", (
        "подъём", "обзор", "уклон", "повороты", "покрытие", "остановки",
        "погода", "багаж", "маршрут", "видимость")),
    "rain": ("Дождливая дорога", "дождливая поездка", (
        "сцепление", "видимость", "покрытие", "одежда", "дистанция",
        "освещение", "лужи", "темп", "маршрут", "погода")),
    "desert": ("Песчаная трасса", "песчаная дорога", (
        "песок", "ориентиры", "подготовка", "вода", "покрытие",
        "темп", "погода", "остановки", "защита", "маршрут")),
    "city": ("Городские улицы", "городское движение", (
        "перекрёсток", "разметка", "дистанция", "светофор", "обзор",
        "пешеходы", "темп", "повороты", "погода", "зеркала")),
    "vintage": ("Классический байк", "классический мотоцикл", (
        "детали", "история", "состояние", "уход", "мастерство",
        "осмотр", "дизайн", "подготовка", "комфорт", "выбор")),
    "roadtrip": ("Мотопутешествие", "мотопутешествие", (
        "маршрут", "отдых", "погода", "багаж", "топливо",
        "обзор", "темп", "связь", "остановки", "подготовка")),
    "training": ("Тренировка", "мототренировка", (
        "площадка", "основа", "повороты", "внимание", "защита",
        "темп", "обратная связь", "прогресс", "план", "контроль")),
    "helmet": ("Экипировка", "выбор экипировки", (
        "шлем", "обзор", "посадка", "защита", "комфорт", "погода",
        "перчатки", "видимость", "состояние", "выбор")),
    "dirt": ("Грунтовая трасса", "езда по грунту", (
        "покрытие", "колея", "влажность", "обзор", "темп",
        "повороты", "защита", "рельеф", "маршрут", "подготовка")),
    "sunset": ("Вечерняя дорога", "вечерняя поездка", (
        "освещение", "горизонт", "обзор", "темп", "погода",
        "маршрут", "отдых", "повороты", "видимость", "настроение")),
    "snow": ("Зимний маршрут", "поездка в холод", (
        "температура", "покрытие", "сцепление", "экипировка", "обзор",
        "погода", "подготовка", "дистанция", "план", "остановки")),
    "racing": ("Гоночная трасса", "мотогонка", (
        "трасса", "траектория", "повороты", "экипировка", "техника",
        "команда", "план", "обзор", "покрытие", "ритм")),
}
ANGLES = (
    ("первый взгляд", "Первое впечатление привлекает внимание, но не раскрывает всего контекста."),
    ("второй ракурс", "Другой ракурс меняет восприятие, даже когда речь идёт об одной теме."),
    ("важная мелочь", "Небольшая деталь может оказаться интереснее эффектного общего плана."),
    ("честный взгляд", "Полезно отличать видимые факты от собственных догадок."),
    ("простое решение", "Спокойная оценка ситуации часто важнее поспешного решения."),
    ("живой контекст", "За короткими кадрами всегда остаётся часть реальной обстановки."),
    ("сравнение", "Сравнивать разные подходы полезнее, чем искать один универсальный ответ."),
    ("новый вопрос", "У привычной мототемы можно найти неожиданный вопрос для обсуждения."),
    ("точка внимания", "Стоит заметить, на что обращаешь внимание с самого начала."),
    ("смысл деталей", "Впечатление складывается не только из движения, но и из мелочей."),
)
LESSONS = (
    ("план", "Понятный план помогает лучше оценить собственные возможности."),
    ("внимание", "Обстановка вокруг заслуживает не меньшего внимания, чем техника."),
    ("подготовка", "Подготовку разумнее закончить до начала поездки или работы."),
    ("без спешки", "Спешка не добавляет ясности, когда условий ещё не знаешь."),
    ("условия", "Реальные условия могут отличаться от того, что видно на экране."),
    ("точность", "Простой вопрос вовремя полезнее поспешного уверенного вывода."),
    ("общий обзор", "Для вывода полезно увидеть общую картину, а не один кадр."),
    ("разумный темп", "Подходящий темп зависит от обстановки, а не от впечатления."),
    ("свой выбор", "Разным людям и мотоциклам подходят разные решения."),
    ("контекст", "Короткое видео даёт повод подумать, но не заменяет опыт."),
)
QUESTIONS = (
    ("твой выбор", "А на что ты обратил бы внимание в первую очередь?"),
    ("что заметил", "Какая деталь показалась тебе самой интересной?"),
    ("куда смотреть", "Какой ракурс ты выбрал бы для следующего видео?"),
    ("в чём смысл", "Что для тебя здесь важнее всего?"),
    ("что важнее", "Что бы ты обсудил с другим райдером?"),
    ("какой момент", "Какой момент ты хотел бы увидеть подробнее?"),
    ("что дальше", "О какой мототеме рассказать в следующей истории?"),
    ("почему так", "А ты видишь эту ситуацию по-другому?"),
    ("твоя версия", "Какой подход тебе кажется разумнее?"),
    ("как считаешь", "Как бы ты объяснил этот выбор другу?"),
)
THEME_KEYS = tuple(THEMES)
PER_THEME = 10_000
RESERVE_CAPACITY = len(THEME_KEYS) * PER_THEME
assert len(THEME_KEYS) == 15
assert all(len(v[2]) == 10 and len(set(v[2])) == 10 for v in THEMES.values())
assert len(ANGLES) == len(LESSONS) == len(QUESTIONS) == 10


def compose(theme_key: str, local_index: int) -> dict:
    """Compose the entire fully-addressable script from four editorial axes."""
    if theme_key not in THEMES:
        raise ValueError("Unknown motorcycle topic")
    if type(local_index) is not int or not 0 <= local_index < PER_THEME:
        raise ValueError("Script reserve index out of range")
    face, angle, lesson, question = (
        local_index // 1000, (local_index // 100) % 10,
        (local_index // 10) % 10, local_index % 10
    )
    display, topic, facets = THEMES[theme_key]
    focus = facets[face]
    a_label, a_line = ANGLES[angle]
    l_label, l_line = LESSONS[lesson]
    q_label, q_line = QUESTIONS[question]
    # All axes also change the headline, not merely an artificial ID.
    title = f"{display}: {focus}, {a_label}, {l_label} — {q_label}? #shorts"
    narration = (f"Мотоцикл и {topic}. {a_line} "
                 f"Отдельная тема — {focus}. {l_line} {q_line}")
    if not 125 <= len(narration) <= 300 or len(title) > 100:
        raise ValueError("Script length outside production limits")
    return {
        "title": title, "narration": narration,
        "description": (f"Самостоятельная мототема: {focus}. "
                        "Кадры иллюстративные, а не запись одного подтверждённого события."
                        "\n\n#shorts"),
        "caption_start": display.upper(),
        "caption_middle": "ВАЖНАЯ ДЕТАЛЬ",
        "caption_end": "А ТВОЙ ВЫБОР?",
        "_generation_source": "offline_editorial_reserve_v2",
        "_reserve_id": f"r2-{theme_key}-{local_index:04d}",
    }


def at(global_index: int) -> dict:
    if type(global_index) is not int or not 0 <= global_index < RESERVE_CAPACITY:
        raise ValueError("Global reserve index out of range")
    return compose(THEME_KEYS[global_index // PER_THEME],
                   global_index % PER_THEME)


def choose(theme_key: str, sources, previous_titles, used_ids=()) -> dict:
    """Avoid old headlines and consumed IDs; every slot is eventually visited."""
    if theme_key not in THEMES:
        raise ValueError("Unknown motorcycle topic")
    titles = {str(x).strip().casefold() for x in previous_titles}
    ids = set(used_ids)
    media = "|".join(str(x.get("source_page") or x.get("key") or "")
                     for x in sources)
    digest = hashlib.sha256((theme_key + "|" + media + "|" +
                             str(len(titles))).encode("utf8")).digest()
    start = int.from_bytes(digest[:8], "big") % PER_THEME
    # gcd(9973, 10000) == 1: no index may be permanently skipped.
    for offset in range(PER_THEME):
        slot = (start + 9973 * offset) % PER_THEME
        proposal = compose(theme_key, slot)
        if proposal["title"].casefold() not in titles and proposal["_reserve_id"] not in ids:
            return proposal
    raise RuntimeError("STORY_RESERVE_THEME_EXHAUSTED: expand editorial axes")


def remaining(used_ids) -> int:
    consumed = set()
    for value in used_ids:
        if not isinstance(value, str) or not value.startswith("r2-"):
            continue
        try:
            prefix, key, raw = value.split("-", 2)
            index = int(raw)
            if (prefix == "r2" and key in THEMES
                    and raw == f"{index:04d}" and 0 <= index < PER_THEME):
                consumed.add(value)
        except (ValueError, TypeError):
            continue
    return RESERVE_CAPACITY - len(consumed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--index", type=int)
    args = parser.parse_args()
    if args.index is not None:
        result = at(args.index)
    else:
        result = {
            "version": VERSION, "total_addressable_scenarios": RESERVE_CAPACITY,
            "themes": len(THEMES), "variants_per_theme": PER_THEME,
            "note": "Narrative variants only; not licensed footage or approved MP4s."
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
