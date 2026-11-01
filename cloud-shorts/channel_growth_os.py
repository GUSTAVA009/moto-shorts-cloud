#!/usr/bin/env python3
"""Seven-pillar growth planning for an autonomous YouTube Factory.

NO rendering, public publishing, spending, fake demand/CTR, fake YPP progress,
or silent niche switch. A 100-idea editorial bank is distinct from MP4 stock.
Optional Studio metrics must be dated, source-backed and comparable in age.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parent
IDEAS=ROOT/"channel_idea_bank_100.json"
PUBLIC=ROOT/"channel_public_snapshot_20261101.json"
CHANNEL="UCS0QCodPcFBTjMt4ioEWOUw"
MIX={"facts":7,"stories":5,"experiments":5,"spectacle":3}
SHORTS_TARGET=400
GOAL_USD=5000
NEW_YPP_DATE=date(2027,2,1)
NICHE_HYPOTHESES=[
    {"niche":"motorcycle","status":"existing_brand_core",
     "strength":"existing audience, prior footage review and creator expertise",
     "evidence_needed":"source-rights supply, mature engaged views, RPM and buyer interest"},
    {"niche":"motorcycle_maintenance","status":"adjacent_test_only",
     "strength":"searchable evergreen instructions with tangible demonstrations",
     "evidence_needed":"original repair footage, search demand, creator competence, safe manuals"},
    {"niche":"moto_safety_gear","status":"adjacent_test_only",
     "strength":"educational evergreen gear questions and potential compliant affiliates",
     "evidence_needed":"product rights, real demonstrations, disclosure and audience fit"},
    {"niche":"motorcycle_travel","status":"adjacent_test_only",
     "strength":"visually distinctive routes and longer-format narrative opportunities",
     "evidence_needed":"owned/usable route videos, travel availability, watch-time baseline"},
    {"niche":"science_explained","status":"separate_channel_research_only",
     "strength":"wide topic runway for reproducible visual explanations",
     "evidence_needed":"demand, qualified expertise, original illustration costs, creator fit"},
    {"niche":"software_ai_tools","status":"separate_channel_research_only",
     "strength":"product search potential but fast obsolescence and higher competition",
     "evidence_needed":"fresh demonstrations, search trend, affiliate suitability, rights"},
]


def verify_bank(bank):
    if bank.get("channel_id")!=CHANNEL or bank.get("total_ideas")!=100:
        raise ValueError("IDEA_BANK_WRONG_CHANNEL_OR_SIZE")
    ideas=bank.get("ideas")
    if not isinstance(ideas,list) or len(ideas)!=100:
        raise ValueError("IDEA_BANK_MUST_HAVE_EXACTLY_100_IDEAS")
    counts=Counter()
    ids=set()
    titles=set()
    for item in ideas:
        for key in ("idea_id","category","title","hook_draft",
                    "thumbnail_caption","required_visual_evidence"):
            if not isinstance(item.get(key),str) or not item[key].strip():
                raise ValueError("IDEA_BANK_INCOMPLETE_"+key)
        if item["idea_id"] in ids or item["title"].casefold() in titles:
            raise ValueError("IDEA_BANK_DUPLICATE")
        if item.get("status")!="research_only_not_scheduled" or item.get(
                "evidence_status")!="IDEA_ONLY_NO_FOOTAGE_RIGHTS":
            raise ValueError("IDEA_MISTAKEN_FOR_APPROVED_MP4")
        if len(item["hook_draft"])>185 or len(item["thumbnail_caption"])>52:
            raise ValueError("IDEA_HOOK_OR_COVER_TOO_LONG")
        counts[item["category"]]+=1
        ids.add(item["idea_id"])
        titles.add(item["title"].casefold())
    if dict(counts)!={k:v*5 for k,v in MIX.items()}:
        raise ValueError("IDEA_BANK_MIX_MISMATCH")
    return ideas


def validate_public(snap):
    if snap.get("channel_id")!=CHANNEL:
        raise ValueError("PUBLIC_METADATA_WRONG_CHANNEL")
    if snap.get("source")!="vidiq_owned_channel_public_metadata":
        raise ValueError("PUBLIC_METADATA_UNAUTHORIZED_SOURCE")
    date.fromisoformat(snap["observed_date"])
    for k in ("subscribers","lifetime_public_views","public_video_count"):
        v=snap.get(k)
        if type(v) is not int or v<0:
            raise ValueError("PUBLIC_METADATA_"+k)
    return snap


def validate_studio(studio):
    if studio is None:
        return None
    if (studio.get("channel_id")!=CHANNEL or
            studio.get("source") not in
            ("official_youtube_studio_export","youtube_analytics_api_oauth")):
        raise ValueError("STUDIO_ANALYTICS_WRONG_CHANNEL_OR_PROVENANCE")
    snapshot_date=date.fromisoformat(studio["observed_date"])
    for field in ("qualified_shorts_views_90d",
                  "qualified_longform_watch_hours_365d","subscribers"):
        val=studio.get(field)
        if val is not None and (isinstance(val,bool) or
                               not isinstance(val,(int,float)) or val<0):
            raise ValueError("STUDIO_METRIC_INVALID_"+field)
    records=studio.get("per_video_48h",[])
    if not isinstance(records,list):
        raise ValueError("STUDIO_VIDEOS_NOT_LIST")
    ids=set()
    for r in records:
        if not isinstance(r,dict) or not r.get("video_id"):
            raise ValueError("STUDIO_VIDEO_MISSING_ID")
        if r["video_id"] in ids:
            raise ValueError("STUDIO_DUPLICATE_VIDEO_MEASUREMENT")
        ids.add(r["video_id"])
        if r.get("category") not in MIX:
            raise ValueError("STUDIO_VIDEO_UNRECOGNIZED_CATEGORY")
        p=datetime.fromisoformat(r["published_at"].replace("Z","+00:00"))
        m=datetime.fromisoformat(r["measured_at"].replace("Z","+00:00"))
        if p.tzinfo is None or m.tzinfo is None or m<p:
            raise ValueError("STUDIO_VIDEO_INVALID_TIMESTAMPS")
        if date.fromtimestamp(m.timestamp())>snapshot_date:
            raise ValueError("STUDIO_VIDEO_FUTURE_MEASUREMENT")
        for k in ("engaged_views","shown_in_feed","subscribers_gained",
                  "views","shares","comments"):
            v=r.get(k)
            if v is not None and (type(v) is not int or v<0):
                raise ValueError("STUDIO_VIDEO_INVALID_"+k)
        for k,ceiling in (("viewed_instead_of_swiped_fraction",1),
                          ("average_percentage_viewed",3)):
            v=r.get(k)
            if v is not None and (not isinstance(v,(int,float))
                                  or isinstance(v,bool) or not 0<=v<=ceiling):
                raise ValueError("STUDIO_VIDEO_INVALID_"+k)
    return studio


def comparable_cohorts(studio):
    """Only one measurement per video, age 48h +/-12h, documented YouTube source."""
    if not studio:
        return {}
    groups=defaultdict(list)
    for r in studio.get("per_video_48h",[]):
        p=datetime.fromisoformat(r["published_at"].replace("Z","+00:00"))
        m=datetime.fromisoformat(r["measured_at"].replace("Z","+00:00"))
        age=(m-p).total_seconds()/3600
        if not 36<=age<=60 or r.get("engaged_views") is None:
            continue
        groups[r["category"]].append(r)
    return dict(groups)


def winner_evidence(studio):
    result={}
    for name,rows in comparable_cohorts(studio).items():
        feed=sum(r.get("shown_in_feed") or 0 for r in rows)
        if len(rows)<3 or feed<500:
            result[name]={"status":"insufficient_equal_age_sample",
                          "observed_videos":len(rows),"shown_in_feed":feed}
            continue
        engaged=[r["engaged_views"] for r in rows]
        subs=sum(r.get("subscribers_gained") or 0 for r in rows)
        result[name]={
            "status":"observed_not_causal",
            "observed_videos":len(rows),
            "median_48h_engaged_views":statistics.median(engaged),
            "subscribers_per_1000_engaged":round(1000*subs/sum(engaged),2)
            if sum(engaged)>0 else None,
            "viewed_instead_of_swiped_fraction_median":statistics.median(
                [r["viewed_instead_of_swiped_fraction"] for r in rows
                 if r.get("viewed_instead_of_swiped_fraction") is not None])
            if any(r.get("viewed_instead_of_swiped_fraction") is not None
                   for r in rows) else None,
            "shown_in_feed":feed,
        }
    return result


def next_test_batch(ideas,studio=None):
    # Deterministic fixed 7/5/5/3 per 20; the seven screenshots do NOT
    # override the owner's pre-existing allocation. No fabricated viral rank.
    evidence=winner_evidence(studio)
    batch=[]
    for category,count in MIX.items():
        candidates=[i for i in ideas if i["category"]==category]
        candidates.sort(key=lambda x: (x["editorial_priority_tier"]!="initial_test",
                                       x["idea_id"]))
        for item in candidates[:count]:
            batch.append({
                "idea_id":item["idea_id"],"category":category,
                "title":item["title"],"hook_draft":item["hook_draft"],
                "thumbnail_caption":item["thumbnail_caption"],
                "required_visual_evidence":item["required_visual_evidence"],
                "priority_basis": "measured_same_age_category_cohort" if
                evidence.get(category,{}).get("status")=="observed_not_causal"
                else "editorial_exploration_not_market_rank",
                "needs_fresh_licensed_footage":True,
                "publishable":False,
                "script_status":"concept_not_produced",
            })
    assert len(batch)==20
    return batch


def monetization(snapshot_date,studio):
    day=date.fromisoformat(snapshot_date)
    subscribers=studio.get("subscribers") if studio else None
    qualified=studio.get("qualified_shorts_views_90d") if studio else None
    hours=studio.get("qualified_longform_watch_hours_365d") if studio else None
    threshold_shorts=20_000_000 if day>=NEW_YPP_DATE else 10_000_000
    threshold_hours=8_000 if day>=NEW_YPP_DATE else 4_000
    official_threshold_met=(subscribers is not None and subscribers>=1000
       and ((qualified is not None and qualified>=threshold_shorts)
            or (hours is not None and hours>=threshold_hours)))
    return {
        "date":snapshot_date,"gross_monthly_revenue_goal_usd":GOAL_USD,
        "goal_is_not_forecast":True,
        "full_ads_new_applicant_thresholds":{
            "subscribers":1000,"qualified_shorts_views_90d":threshold_shorts,
            "qualified_longform_watch_hours_365d":threshold_hours},
        "official_eligibility_observed":bool(studio is not None and
           subscribers is not None and (qualified is not None or hours is not None)),
        "thresholds_met_on_official_snapshot":official_threshold_met if studio else None,
        "ypp_approval_or_monetization_guaranteed":False,
        "paths":[
            {"kind":"ads_and_youtube_premium","requires":"YPP country and eligibility plus approval"},
            {"kind":"sponsorships","requires":"verified audience fit, written brand agreement and disclosure"},
            {"kind":"affiliate","requires":"genuine useful product tests, valid disclosure and regional legality"},
            {"kind":"digital_products","requires":"original checklists or instructional materials and actual buyer demand"},
            {"kind":"community_or_memberships","requires":"real community value and platform eligibility"},
        ],
        "shorts_creator_pool_2027_condition":
            "From 2027-02-01, maintaining 10M qualified Shorts views/90 days "
            "is required for monthly Shorts Creator Pool earnings; "
            "other approved YPP revenue sources may still apply.",
    }


def compose(public,bank,studio=None):
    ideas=verify_bank(bank)
    public=validate_public(public)
    studio=validate_studio(studio)
    as_of=studio["observed_date"] if studio else public["observed_date"]
    winners=winner_evidence(studio)
    result={
        "channel_id":CHANNEL,"as_of":as_of,
        "real_public_metadata":{"as_of":public["observed_date"],
            "subscribers":public["subscribers"],
            "lifetime_public_views":public["lifetime_public_views"],
            "public_video_count":public["public_video_count"],
            "note":"Public counters do not equal eligible Shorts views or 48h retention"},
        "official_youtube_studio_connected":studio is not None,
        "official_snapshot_date":studio["observed_date"] if studio else None,
        "experiment_evidence":winners,
        "no_verified_winner_if_insufficient_data":not any(
            x["status"]=="observed_not_causal" for x in winners.values()),
        "approved_distribution_20":MIX,
        "next_20_editorial_briefs":next_test_batch(ideas,studio),
        "total_research_ideas":len(ideas),
        "ideas_are_not_scripts_or_mp4s":True,
        "niche_research_not_unilateral_niche_switch":NICHE_HYPOTHESES,
        "monetization":monetization(as_of,studio),
        "release_gate":"footage_license + visual proof + independent TTS + "
                       "source/mixed ASR + original edit QA + manual/approved "
                       "editorial review + Buffer ID + publicly visible YouTube URL",
        "priority_experiments":[
            "Test action-first vs honest question-first opening in separate original videos",
            "Compare actual scene changes against verified narration anchors",
            "Test educational fact vs documentary micro-story with equal-age engaged views",
            "Track audience retention and new subscribers; do not rank by raw first-frame views alone",
        ],
        "required_kpi_sources":{
           "public_channel_counts":"vidIQ connected account metadata (snapshot dated)",
           "qualified_ypp":"YouTube Studio Earn verified dated snapshot only",
           "age_48h_engaged_views":"YouTube Analytics OAuth or truthful Studio export",
           "shorts_stayed_to_watch":"YouTube Studio Shorts analytics (not impressions CTR)",
           "longform_impressions_ctr":"YouTube Studio Reach (long-form only)",
           "revenue":"YouTube Earn and actual payout ledger; otherwise unknown",
        },
        "missing_data_notes":[
            "vidIQ detailed analytics blocked by exhausted credits; do not invent values"
        ] if not studio else [],
        "safe_to_auto_rebalance_channel_niche":False,
        "safe_to_auto_publish_concept_ideas":False,
    }
    return result


def markdown(plan):
    p=plan["real_public_metadata"]
    rows=[
        "# Семь направлений YouTube Factory — стратегический цикл","",
        "Датированный отчёт: **"+plan["as_of"]+"**. "
        "Репозиторий не производит и не публикует видео этим анализом.","",
        "## 1. Полный план канала",
        "Позиционирование: русскоязычные оригинальные мотоистории, "
        "конкретная польза и зрелищные реальные кадры. "
        "Shorts приводят зрителей к связанным длинным обзорам и плейлистам.",
        "Неделя 1: диагностика источников, голоса и публикаций. "
        "Неделя 2: 20 фактически разных оригинальных концепций, "
        "строгая проверка лицензий и narration↔scene.",
        "Неделя 3: равновозрастные тесты хуков и сериальных рубрик. "
        "Неделя 4: сравнение результата и только обоснованная следующая партия.",
        "",
        "## 2. Выбор ниши и 100 идей",
        "100 подготовленных **идей**, не 100 сценариев и не 100 MP4. "
        "Рабочая ниша не меняется без подтверждённых метрик.",
        "Каждая идея содержит тему, хук, надпись обложки и требуемые "
        "реальные исходники. Наличие идеи не доказывает спрос.","",
        "## 3. Хуки, заголовки, обложки и удержание",
        "Первые 0–2 секунды: реальное действие, понятный вопрос или "
        "честный контраст без ложного обещания.",
        "Середина: эскалация и соответствующий словам кадр; "
        "финал: проверяемая развязка + один ненавязчивый призыв.",
        "Текст обложки 2–6 читаемых слов и кадр, действительно "
        "присутствующий в ролике. Шаблон запрещено выдавать за оригинальный сценарий.",
        "",
        "## 4. Рост и алгоритмическая обратная связь",
        "Основные КПИ: (1) подтверждённые публичные оригинальные Shorts "
        "за месяц относительно 400; (2) медиана engaged views "
        "на одинаковом возрасте 48±12 часов; (3) подписки на "
        "1000 вовлечённых просмотров.",
        "Диагностика: stayed-to-watch, retention, shares, traffic "
        "source, возвращающиеся зрители. CTR impressions — отдельный "
        "показатель для обложек длинных видео, не замена метрике Shorts swipe.",
        "",
        "## 5. Производственный конвейер без ручного ChatGPT",
        "Актуальный процесс: новые лицензированные сюжеты → оригинальный "
        "сценарий → разрешённые HTTPS TTS маршруты → монтаж FFmpeg → "
        "ASR и кадры → QA → Buffer → публичная ссылка. "
        "Используйте шаблоны проверок, не штампуйте одинаковое содержание.",
        "",
        "## 6. Монетизация",
        "Цель $5 000/месяц — **желаемая валовая выручка, не прогноз**. "
        "Нужны реальные данные о доходе и географии. "
        "Каналы выручки: YPP реклама, спонсорство, легальные партнёрские "
        "программы с маркировкой, собственные обучающие продукты и сообщество.",
        "Критерии YPP для новых заявителей на дату отчёта: "+
        str(plan["monetization"]["full_ads_new_applicant_thresholds"]["subscribers"])+
        " подписчиков и (часы: "+
        str(plan["monetization"]["full_ads_new_applicant_thresholds"]["qualified_longform_watch_hours_365d"])+
        " или Shorts: "+
        str(plan["monetization"]["full_ads_new_applicant_thresholds"]["qualified_shorts_views_90d"])+
        "). Допускается только проверенный официальной панелью прогресс.",
        "",
        "## 7. Еженедельная и ежемесячная аналитика",
        "Проверка: публикации по живым YouTube URL, одновозрастные "
        "engaged views и удержание, прирост подписчиков, "
        "источники трафика, фактический доход.",
        "Не принимать победителя из <3 сопоставимых Shorts или "
        "<500 показов в ленте на направление; менять сетку 7/5/5/3 "
        "только после достоверного теста и решения владельца.",
        "",
        "### Измеренная публичная база",
        "Подписчики: **"+str(p["subscribers"])+
        "**; просмотры за всё время: **"+str(p["lifetime_public_views"])+
        "**; публичных роликов: **"+str(p["public_video_count"])+
        "** (дата "+p["as_of"]+"). Это НЕ Studio Earn и НЕ 48-часовые измерения.","",
        "### Результаты гипотез",
        "Доступных для вывода достоверных сравнимых групп: **"+
        str(sum(x["status"]=="observed_not_causal" for x
                in plan["experiment_evidence"].values()))+"**.",
        "Детальная аналитика: **"+("доступна" if plan["official_youtube_studio_connected"]
            else "не подключена")+"**. Нельзя выдумывать CTR, RPM и удержание.","",
        "### Первая двадцатка концепций — НЕ очередь MP4","",
        "| № | Рубрика | Идея | Публикация |",
        "|---:|---|---|---|",
    ]
    for i,item in enumerate(plan["next_20_editorial_briefs"],1):
        rows.append("| "+str(i)+" | "+item["category"]+" | "+
                    item["title"].replace("|","/")+" | Нет исходников и QA |")
    rows.extend(["","Официальные правила:",
         "- https://support.google.com/youtube/answer/72851",
         "- https://support.google.com/youtube/answer/12843009",
         "- https://support.google.com/youtube/answer/1311392",
         "- https://support.google.com/youtube/answer/12942217",""])
    return "\n".join(rows)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ideas",type=Path,default=IDEAS)
    p.add_argument("--public",type=Path,default=PUBLIC)
    p.add_argument("--studio-json",type=Path)
    p.add_argument("--out-dir",type=Path,default=ROOT/"dist"/"growth-os")
    args=p.parse_args()
    read=lambda f:json.loads(f.read_text(encoding="utf8"))
    plan=compose(read(args.public),read(args.ideas),
                 read(args.studio_json) if args.studio_json else None)
    args.out_dir.mkdir(parents=True,exist_ok=True)
    (args.out_dir/"growth-plan.json").write_text(
        json.dumps(plan,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    (args.out_dir/"weekly-and-monthly-plan.md").write_text(
        markdown(plan),encoding="utf8")
    (args.out_dir/"next-20-research-briefs.json").write_text(
        json.dumps(plan["next_20_editorial_briefs"],ensure_ascii=False,indent=2)+"\n",
        encoding="utf8")
    print("GROWTH_OS_REPORT_READY 100_CONCEPTS 20_RESEARCH_BRIEFS "
          "NO_PUBLICATION_NO_FAKE_STUDIO_METRICS")
    if not plan["official_youtube_studio_connected"]:
        print("::warning::GROWTH_OS_STUDIO_ANALYTICS_UNAVAILABLE;"
              " ranked creator hypotheses only, no fake niche profit scores")


if __name__=="__main__":
    main()
