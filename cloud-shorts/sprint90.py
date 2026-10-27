#!/usr/bin/env python3
"""90-day YouTube Partner Program progress and urgency tracker.

The official Earn page can be DAYS behind; never combine counts observed at
different timestamps to claim real-time eligibility. This script reports
math/unknowns, not guaranteed growth or revenues.
"""
from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING
import argparse
import json
from pathlib import Path

HERE=Path(__file__).parent
TARGET_SUBS=1000
TARGET_SHORTS=10_000_000
TARGET_HOURS=4000
WINDOW_DAYS=90

def ceiling(a,b):
    if b<=0: raise ValueError("Divisor must be positive")
    return (a+b-1)//b

def required_metrics(baseline:dict, active_days=90, planned_publishes=45):
    if not 1 <= active_days <= 365 or not 1 <= planned_publishes <= 365:
        raise ValueError("Invalid scenario assumptions")
    m=baseline.get("monetization",{})
    if m.get("eligibility_snapshot_date") is None:
        raise ValueError("Official dated YouTube Earn snapshot required")
    subs=int(baseline["subscribers"])
    eligible_short=int(m["qualified_shorts_views_90d"])
    watch_hours=float(m["qualified_longform_watch_hours_365d"])
    if any(x<0 for x in (subs,eligible_short,watch_hours)):
        raise ValueError("Negative counters invalid")
    short_gap=max(0,TARGET_SHORTS-eligible_short)
    hours_gap=max(0,TARGET_HOURS-watch_hours)
    sub_gap=max(0,TARGET_SUBS-subs)
    return {
        "subscriber_current": subs,
        "subscriber_gap":sub_gap,
        "subscriber_90d_pace":ceiling(sub_gap,active_days),
        "qualified_shorts_current_asof":eligible_short,
        "qualified_shorts_gap":short_gap,
        "shorts_daily_required_scenario":ceiling(short_gap,active_days),
        "shorts_average_per_new_upload_scenario":ceiling(short_gap,planned_publishes),
        "longform_hours_current_asof":watch_hours,
        "longform_hours_gap":hours_gap,
        "longform_views_if_5_minutes_average":ceiling(int(hours_gap*60),5),
        "earn_progress_data_as_of":m["eligibility_snapshot_date"],
        "ypp_approved":m.get("ypp_enabled") is True,
        "two_step_verification_complete":m.get("two_step_verification_required") is False,
        "payments_country_verified":bool(m.get("verified_adsense_country")),
    }

def recommendations(metrics):
    # This system is designed to optimize actual *engaged* views,
    # and to recognize when longform watch hours are a more plausible path.
    decisions=[]
    if not metrics["two_step_verification_complete"]:
        decisions.append("ACTION REQUIRED BY OWNER: enable Google 2-Step Verification in YouTube Studio Earn.")
    if not metrics["payments_country_verified"]:
        decisions.append("VERIFY: legal YPP region and AdSense payout country; public channel country RU is not proof.")
    decisions.append("TRACK: eligible engaged Shorts views on the official Earn page, not raw public video views.")
    decisions.append("RUN: 1 original non-template short per available publishing day; change story, people, motorcycles and location.")
    decisions.append("RUN: 1 research-checked original 5-10-minute video weekly to build the alternate 4000-hour route.")
    decisions.append("DO NOT: inflate watch time/subscribers, mirror viral content, mass-produce indistinguishable stock compilations.")
    return decisions

def markdown(baseline,metrics,days,planned_publishes):
    subs=metrics["subscriber_current"]
    snapshot=metrics["earn_progress_data_as_of"]
    lines=[
        "# 90-дневный спринт к монетизации",
        "",
        f"**Реальный раздел YouTube Studio → Монетизация, данные на {snapshot}.**",
        "Не обновляйте проценты квалифицированных просмотров на основе более свежего публичного счётчика Shorts.",
        "",
        "| Метрика | Факт с датой снимка | Порог | Осталось |",
        "|---|---:|---:|---:|",
        f"| Подписчики | {subs:,} | {TARGET_SUBS:,} | {metrics['subscriber_gap']:,} |",
        f"| Квалифицированные просмотры Shorts за 90 дней | {metrics['qualified_shorts_current_asof']:,} | {TARGET_SHORTS:,} | {metrics['qualified_shorts_gap']:,} |",
        f"| Учитываемые часы длинных видео за 365 дней | {metrics['longform_hours_current_asof']:,} | {TARGET_HOURS:,} | {metrics['longform_hours_gap']:,} |",
        "",
        "## Какие показатели придётся достичь",
        "",
        f"При **условных** {days} днях и {planned_publishes} новых качественных Shorts за этот период:",
        f"- {metrics['shorts_daily_required_scenario']:,} подходящих Shorts-просмотров в среднем ежедневно.",
        f"- {metrics['shorts_average_per_new_upload_scenario']:,} подходящих просмотров в среднем на новый Short "
        "(если почти всё необходимо набрать новыми публикациями; это не прогноз).",
        f"- {metrics['subscriber_90d_pace']:,} новых подписчиков ежедневно в среднем.",
        f"- Альтернатива: {metrics['longform_hours_gap']:,} часов просмотра длинных видео, "
        f"что эквивалентно примерно {metrics['longform_views_if_5_minutes_average']:,} просмотрам "
        "с **реальной средней длительностью 5 минут**.",
        "",
        "**Важно:** Shorts-порог — скользящие 90 дней; просмотры из старых дней будут выпадать. "
        "Прошлые просмотры не обязаны оставаться в окне. Оценка выше — иллюстрация скорости, "
        "не обещание выполнения. Новые Shorts не гарантируют включение YPP, требуется проверка оригинальности и страны.",
        "",
        "## Блокеры и действия",
        ""
    ]
    for n,action in enumerate(recommendations(metrics),start=1):
        lines.append(f"{n}. {action}")
    lines.extend([
        "",
        "## Как выбираем творческие эксперименты",
        "",
        "| Направление | Приём первого кадра | Собственная ценность | Длина для теста |",
        "|---|---|---|---|",
        "| Реальное спасение от падения | Райдер уже теряет равновесие | Разбор причин и развязки с доказуемыми кадрами | 20–30 с |",
        "| Гараж и ошибки обслуживания | Сразу видна проблема/деталь | Проверяемое объяснение с опорой на мануал | 20–35 с |",
        "| Сравнение разных мотоциклов | Контраст двух моделей | Собственное сравнение возможностей и ограничений | 25–40 с |",
        "| Необычный маршрут и выбор | Показать препятствие до объяснений | Обоснование решения/реальная история | 20–35 с |",
        "| Длинный полезный разбор | Точный вопрос за первые 10 с | 5–10 мин авторского анализа, не слайдшоу | 5–10 мин |",
        "",
        "Не копировать чужую подборку падений или чужой монтаж. У каждого видео — свой авторский сценарий, "
        "оригинальное объяснение, разрешённые исходные кадры. Подлинная вероятность успеха выясняется "
        "лишь по публикациям и аналитике.",
        "",
        "## Основные ссылки",
        "",
        "- YouTube Studio Earn: https://studio.youtube.com/channel/"
        +baseline["channel_id"]+"/monetization",
        "- YPP официально: https://support.google.com/youtube/answer/72851",
        "- Политика оригинальности: https://support.google.com/youtube/answer/1311392",
        "- Канал: https://www.youtube.com/channel/"+baseline["channel_id"],
        "",
    ])
    return "\n".join(lines)+"\n"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--baseline",type=Path,default=HERE/"growth_baseline.json")
    p.add_argument("--days",type=int,default=90)
    p.add_argument("--new-uploads",type=int,default=45)
    p.add_argument("--output",type=Path,default=HERE/"dist"/"sprint90.md")
    args=p.parse_args()
    b=json.loads(args.baseline.read_text(encoding="utf8"))
    metrics=required_metrics(b,args.days,args.new_uploads)
    report=markdown(b,metrics,args.days,args.new_uploads)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(report,encoding="utf8")
    print(report)

if __name__=="__main__":
    main()
