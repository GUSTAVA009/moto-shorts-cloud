#!/usr/bin/env python3
"""Autonomous recovery of ORIGINAL motorcycle drafts from stale A/B comparison formulas.

Converts only never-rendered, unpublished, SHA-licensed, owner-produced two-shot
drafts into a UNIQUE source-grounded practical micro-guide. Never approves or
uploads a video. Existing render/upload receipts are absolute exclusion gates.
The normal independent visual+Russian voice/MP4 gate still controls publishing.
"""
from __future__ import annotations
import argparse
import base64
from copy import deepcopy
import json
import os
import re
import sys
import urllib.parse
import urllib.request

from editorial_novelty import is_generic_unrelated_comparison, require_novel_visual_story
from source_story import scene_for, require_filmable
from moto_assets import validated_media
from render_episode import validate_episode

CHANNEL = "UCS0QCodPcFBTjMt4ioEWOUw"
REPO = "GUSTAVA009/moto-shorts-cloud"
CATALOG = "cloud-shorts/episodes.json"
MAX_PER_CYCLE = 3

# Each source category can be used for only ONE educational story per
# treatment. No replacing a title or SHA to recycle a micro-guide next week.
TREATMENTS = {
    "city+forest": (
        "Почему мотоцикл в лесу требует другого внимания? #shorts",
        "В городе важен обзор перекрёстков. На лесной тропе внимательно смотри на покрытие и препятствия.",
        "РАЗНЫЙ ОБЗОР", "ПОКРЫТИЕ МЕНЯЕТСЯ", "СМОТРИ ВПЕРЁД",
    ),
    "jump+ride": (
        "Прыжок на мотоцикле: подготовка важнее смелости #shorts",
        "Трамплин не про показную смелость. Отрабатывай элементы только в безопасных условиях подготовленного трека.",
        "НЕ ПРОСТО ПРЫЖОК", "ТРЕК И ПОДГОТОВКА", "НЕ ПОВТОРЯЙ НА ДОРОГЕ",
    ),
    "forest+jump": (
        "Лесная тропа — не площадка для мотопрыжка #shorts",
        "Прыжок тренируют на подготовленной трассе. Лесная тропа полна невидимых препятствий: не превращай маршрут в трюковую арену.",
        "НЕ ПУТАЙ УСЛОВИЯ", "ТРАССА И ТРОПА", "БЕЗ ТРЮКОВ В ЛЕСУ",
    ),
    "mud+ride": (
        "Мотоцикл в грязи: почему сцепление меняется #shorts",
        "Поездка по грязи не похожа на ровную трассу. На скользком покрытии особенно важны плавность и запас пространства.",
        "ГРЯЗЬ МЕНЯЕТ ПРАВИЛА", "СЦЕПЛЕНИЕ ДРУГОЕ", "ДЕЙСТВУЙ ПЛАВНО",
    ),
    "city+ride": (
        "Город и мототрек: где нужна особая внимательность #shorts",
        "На городской улице неожиданности часто приходят от других участников. На треке условия и правила совсем другие.",
        "ГОРОД И ТРЕК", "РАЗНЫЕ РИСКИ", "НЕ СПЕШИ",
    ),
    "helmet+mountain": (
        "Шлем перед горной мотопоездкой: важна посадка #shorts",
        "Шлем проверяют и застёгивают до старта. На горной дороге уже поздно подгонять экипировку: безопасность начинается заранее.",
        "ПЕРЕД СТАРТОМ", "ПРОВЕРЬ ШЛЕМ", "ДО ГОРНОЙ ДОРОГИ",
    ),
    "helmet+repair": (
        "Две проверки мотоциклиста до выезда #shorts",
        "Надеть и застегнуть шлем мало. Перед дорогой также полезно проверить мотоцикл: крепёж и состояние техники не любят спешки.",
        "ДО ВЫЕЗДА", "ШЛЕМ И ТЕХНИКА", "НЕ ТОРОПИСЬ",
    ),
    "mud+repair": (
        "После грязевой поездки проверь мотоцикл #shorts",
        "Грязная колея нагружает технику. Отдельная сцена с механиком напоминает: после таких поездок стоит внимательно осмотреть мотоцикл.",
        "ПОСЛЕ ГРЯЗИ", "ОСМОТ В МАСТЕРСКОЙ", "БЕЗ СПЕШКИ",
    ),
    "city+mud": (
        "Городской асфальт и грязная колея: разные риски #shorts",
        "В городе важно видеть поток машин. В грязной колее меняется сцепление: условия на мотоцикле не прощают невнимательность.",
        "РАЗНЫЕ ДОРОГИ", "СЦЕПЛЕНИЕ И ОБЗОР", "БУДЬ ВНИМАТЕЛЕН",
    ),
    "forest+ride": (
        "Лесная дорога на мотоцикле: главная ошибка спешки #shorts",
        "Поездка по лесной дороге требует обзора и пространства для реакции. Даже на привычном мотоцикле не стоит гнаться за кадром.",
        "ЛЕСНАЯ ДОРОГА", "ДЕРЖИ ЗАПАС", "НЕ ГОНЯЙСЯ ЗА КАДРОМ",
    ),
    "mountain+ride": (
        "Серпантин на мотоцикле: думай на поворот вперёд #shorts",
        "В горах обзор ограничен поворотами. Обычная поездка напоминает главное: оцени дорожное покрытие заранее, а не в последний миг.",
        "ГОРНЫЙ МАРШРУТ", "ОБЗОР ВПЕРЁД", "НЕ СПЕШИ",
    ),
    "repair+wheel": (
        "Колесо мотоцикла: почему мелкий осмотр важен #shorts",
        "Механик проверяет мотоцикл, а другой мастер работает с колесом. Регулярный осмотр помогает заметить проблему до дороги.",
        "ПЕРЕД ДОРОГОЙ", "КОЛЕСО И КРЕПЁЖ", "ОСМОТР ВАЖЕН",
    ),
}


def propose(episode, already_used):
    if (episode.get("auto_preview") is not True
            or episode.get("auto_publish") is not False
            or episode.get("editorial_rejected") is True
            or episode.get("visual_review_failed") is True
            or episode.get("voice_engine") != "gustava_selfhosted_qwen3"
            or episode.get("voice_profile") != "gustava_cartoon_b_qwen3_v1"
            or episode.get("editorial_format") != "source_anchored_action_contrast"
            or not is_generic_unrelated_comparison(episode)):
        return None
    sources = episode.get("footage") or []
    if len(sources)!=2 or not all(s.get("license")=="LTX OpenRAIL-M" for s in sources):
        return None
    try:
        for src in sources:
            validated_media(src)
        scenes = [scene_for(x) for x in sources]
    except (ValueError,KeyError,TypeError):
        return None
    if any(not s for s in scenes):
        return None
    pair = "+".join(sorted(s[0] for s in scenes))
    if pair not in TREATMENTS or pair in already_used:
        return None
    title, insight, a, b, c = TREATMENTS[pair]
    action1,action2 = [scene[3] for scene in scenes]
    # The chronology ALWAYS follows the ACTUAL source order. Do not claim
    # both videos filmed a single incident or show one rider.
    lead_options = (
        f"Мотоцикл: сначала {action1}. В другом кадре {action2}. ",
        f"На первом видео {action1}. На второй записи {action2}. ",
        f"Мотоцикл в кадре: {action1}. Отдельно {action2}. ",
    )
    # Keep the real voice synchronized to 2 x 6.7 s ORIGINAL moving clips.
    narrations = [lead + insight for lead in lead_options
                  if 125 <= len(lead+insight) <= 160]
    if not narrations:
        return None
    ep = deepcopy(episode)
    ep.update({
        "title":title,
        "narration":narrations[0],
        "description":(
           insight+" Два независимых иллюстративных видео; не один заезд.\n\n#мото #Shorts"
        ),
        "caption_start":a,"caption_middle":b,"caption_end":c,
        "editorial_format":"original_action_microguide_v1",
        "creative_treatment":"microguide_"+pair.replace("+","_"),
        "generation_provenance":"Unattended source-grounded microguide, immutable owner LTX originals",
        "auto_preview":True, "auto_publish":False,
    })
    try:
        require_filmable(ep, ep["footage"])
        validate_episode(ep)
        require_novel_visual_story(ep, [episode])
    except (ValueError,KeyError,TypeError):
        return None
    return ep


def repair_catalog(catalog, excluded_ids=(), max_changes=MAX_PER_CYCLE):
    updated=deepcopy(catalog)
    original=updated.get("episodes")
    if not isinstance(original,list):
        raise ValueError("BAD_CATALOG")
    excluded=set(excluded_ids)
    used=set()
    for e in original:
        treatment=e.get("creative_treatment") or ""
        if isinstance(treatment,str) and treatment.startswith("microguide_"):
            used.add(treatment.removeprefix("microguide_").replace("_","+"))
    changed=[]
    titles={str(e.get("title") or "").casefold() for e in original}
    # Newer owner LTX sources first; no rewrites of published/previously rendered.
    for i in reversed(range(len(original))):
        if len(changed)>=max_changes:
            break
        e=original[i]
        if e.get("id") in excluded:
            continue
        result=propose(e,used)
        if result is None or result["title"].casefold() in titles:
            continue
        pair=result["creative_treatment"].removeprefix("microguide_").replace("_","+")
        original[i]=result
        changed.append(result["id"])
        used.add(pair)
        titles.add(result["title"].casefold())
    return updated,changed


def gh(url,method="GET",payload=None):
    key=os.environ.get("GITHUB_TOKEN")
    repo=os.environ.get("GITHUB_REPOSITORY")
    if not key or repo!=REPO:
        raise RuntimeError("GITHUB_OWNER_ACTIONS_AUTH_MISSING_OR_WRONG_REPO")
    target="https://api.github.com/repos/"+repo+"/"+url
    data=json.dumps(payload).encode("utf8") if payload is not None else None
    headers={"Authorization":"Bearer "+key,"Accept":"application/vnd.github+json",
             "Content-Type":"application/json","X-GitHub-Api-Version":"2022-11-28",
             "User-Agent":"GUSTAVA-original-microguide-autonomy"}
    req=urllib.request.Request(target,method=method,data=data,headers=headers)
    with urllib.request.urlopen(req,timeout=45) as r:
        return json.load(r) if r.status!=204 else {}


def do_run(dry_run=False):
    if os.environ.get("GITHUB_REPOSITORY")!=REPO:
        raise RuntimeError("WRONG_REPOSITORY")
    # All known previous rendering, Buffer, and direct receipt namespaces
    # exclude retries. Missing or truncated receipt ledger is an error.
    render=gh("git/trees/render-ledger?recursive=1")
    upload=gh("git/trees/upload-ledger?recursive=1")
    if render.get("truncated") or upload.get("truncated"):
        raise RuntimeError("INCOMPLETE_LEDGER_STOP_NO_RETRY")
    excluded=set()
    for node in [*render.get("tree",[]),*upload.get("tree",[])]:
        path=node.get("path","")
        if path.startswith(("render-receipts/","publication-receipts/",
                            "buffer-publication-receipts/","upload-receipts/by-episode/")):
            excluded.add(path.rsplit("/",1)[-1].removesuffix(".json"))
    row=gh("contents/"+CATALOG+"?ref=main")
    raw=base64.b64decode(row["content"])
    catalog=json.loads(raw)
    revised, changed=repair_catalog(catalog,excluded)
    print("ORIGINAL_MICROGUIDE_CANDIDATES",changed,"BLOCKED_RECEIPTS",len(excluded),flush=True)
    if not changed or dry_run:
        return
    # Strict existing schema validation on all episodes, not a bypass.
    from editorial_guard import validate_catalog
    validate_catalog(revised)
    raw=json.dumps(revised,ensure_ascii=False,indent=2)+"\n"
    gh("contents/"+CATALOG,method="PUT",payload={
        "branch":"main","sha":row["sha"],
        "message":"Autonomously replace repetitive unpublished A/B scripts with distinct source-grounded motorcycle microguides",
        "content":base64.b64encode(raw.encode("utf8")).decode("ascii"),
    })
    print("AUTONOMOUS_GROUNDED_DRAFTS_COMMITTED",changed,flush=True)
    # GITHUB_TOKEN content commits do NOT trigger normal push workflows.
    # Request safe resume which itself refuses dispatch if a render is active.
    gh("actions/workflows/factory-resume.yml/dispatches",method="POST",
       payload={"ref":"main"})
    print("AUTOMATIC_RENDER_RECOVERY_DISPATCHED",flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--dry-run",action="store_true")
    args=p.parse_args()
    try:
        do_run(args.dry_run)
    except Exception as exc:
        print("MICROGUIDE_AUTOMATION_STOPPED",type(exc).__name__,
              str(exc)[:240],file=sys.stderr)
        sys.exit(1)
