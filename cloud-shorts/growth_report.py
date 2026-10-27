#!/usr/bin/env python3
"""Honest audience/revenue goal calculator for the verified channel snapshot.

This is NOT a predictor of guaranteed views, earnings or eligibility.
It never posts, purchases engagement or handles AdSense credentials.
"""
from __future__ import annotations
import argparse
from decimal import Decimal, ROUND_CEILING
import json
import os
from pathlib import Path

ROOT = Path(__file__).parent
BASELINE = ROOT / "growth_baseline.json"
RATES = ("0.02", "0.05", "0.10")  # USD per 1,000 views; illustrative, not channel RPM.


def views_for_revenue(goal_usd, rpm_usd):
    goal = Decimal(str(goal_usd))
    rpm = Decimal(str(rpm_usd))
    if goal < 0 or rpm <= 0:
        raise ValueError("Revenue must be nonnegative and RPM positive")
    return int((goal * 1000 / rpm).quantize(Decimal("1"),rounding=ROUND_CEILING))


def funnel(video, subs_from_video=None, engaged_views=None, shares=None):
    views = int(video.get("views", 0))
    likes = video.get("likes")
    comments = video.get("comments")
    result = {
        "views":views,
        "like_rate_percent":round(100 * likes / views, 2) if views > 0 and likes is not None else None,
        "comment_rate_percent":round(100 * comments / views, 2) if views > 0 and comments is not None else None,
        "share_rate_percent":round(100 * shares / views, 2) if views > 0 and shares is not None else None,
        "subscriber_per_1000_engaged": (
            round(1000 * subs_from_video / engaged_views,2)
            if engaged_views and subs_from_video is not None else None
        ),
    }
    return result


def report(data):
    subscribers = int(data["subscribers"])
    goal_subs = int(data["goals"]["subscriber_milestone"])
    goal_usd = Decimal(str(data["goals"]["gross_monthly_income_usd"]))
    current = data["last_public_short"]
    metrics = funnel(current)
    scenarios = {
        rpm: views_for_revenue(goal_usd, rpm)
        for rpm in RATES
    }
    return {
        "subscribers": subscribers,
        "subscriber_gap": max(0,goal_subs - subscribers),
        "subscriber_goal":goal_subs,
        "gross_income_goal_usd":float(goal_usd),
        "actual_income_usd":data["monetization"].get("actual_monthly_income_usd"),
        "ypp_enabled":data["monetization"].get("ypp_enabled"),
        "monetization_country_verified":bool(data["monetization"].get("adsense_country")),
        "video":current,
        "engagement":metrics,
        "illustrative_shorts_views_for_5000usd":scenarios,
    }


def markdown(r, observed):
    fmt=lambda n:"нет данных" if n is None else f"{n:,}".replace(","," ")
    rate=lambda n:"нет данных" if n is None else f"{n:.2f}%"
    v=r["video"]
    lines=[
        "# Прирост канала и путь к $5 000/мес",
        "",
        f"**Снимок данных: {observed}.** Это не обновляемые в реальном времени показатели.",
        f"**Подписчики:** {fmt(r['subscribers'])} / {fmt(r['subscriber_goal'])}; "
        f"до цели нужно ещё {fmt(r['subscriber_gap'])}.",
        f"**Последний опубликованный Short:** {fmt(v['views'])} просмотров, "
        f"{fmt(v.get('likes'))} лайков, {fmt(v.get('comments'))} комментариев.",
        f"**Доля лайков:** {rate(r['engagement']['like_rate_percent'])}; "
        f"доля комментариев: {rate(r['engagement']['comment_rate_percent'])}.",
        "**Подписки с конкретного ролика / на 1 000 вовлечённых просмотров:** "
        "пока нет данных. Не подменять отсутствующие цифры общим числом подписчиков.",
        "",
        "## Только рекламный доход Shorts — иллюстративная математика",
        "",
        "| Гипотетический RPM Shorts | Просмотры за месяц для $5 000 |",
        "|---|---:|",
    ]
    for rpm,views in r["illustrative_shorts_views_for_5000usd"].items():
        lines.append(f"| \${rpm} / 1 000 просмотров | {fmt(views)} |")
    lines.extend([
        "",
        "RPM здесь — допущение для расчёта, **не фактический RPM этого канала**.",
        "Расчёт применим только при доступной и включённой рекламной монетизации. "
        "Если у канала неактивен YPP или не подходит AdSense, рекламный доход = 0.",
        "Цель $5 000 указана как **выручка до затрат и налогов**, а не чистая прибыль.",
        "",
        "## Приоритетные метрики (на каждый новый выпуск)",
        "",
        "1. Прирост подписчиков на 1 000 *вовлечённых* просмотров Shorts.",
        "2. Досмотры: удержание на 1/3 секунде и в конце, средний процент просмотра.",
        "3. Комментарии на 1 000 вовлечённых просмотров, репосты и лайки.",
        "4. Темп просмотров 24/48 часов и возвращающиеся зрители.",
        "5. Доходы по реальным выплатам: YouTube, договоры со спонсорами, "
        "партнёрские продажи, собственные продукты. Отдельно учитываются расходы.",
        "",
        "## Правила роста",
        "",
        "- Только разные сценарии, обстановка, мотоциклы и участники.",
        "- Один тематический призыв к действию на видео: подписка, комментарий, лайк или репост.",
        "- Никогда не накручивать просмотры/подписки, не обмениваться подписками.",
        "- Развивать оригинальные длинные ролики с полезным содержанием и собственным анализом.",
        "- Подтверждать право на кадры и оригинальность до публикации.",
        "- Сначала проверить раздел «Монетизация» YouTube Studio и правовой статус AdSense.",
    ])
    return "\n".join(lines)+"\n"


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--baseline",type=Path,default=BASELINE)
    p.add_argument("--output",type=Path,default=ROOT/"dist"/"growth-report.md")
    a=p.parse_args()
    data=json.loads(a.baseline.read_text(encoding="utf8"))
    result=report(data)
    out=markdown(result,data["measured_date"])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(out,encoding="utf8")
    print(out)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf8") as fh:
            fh.write(out)


if __name__=="__main__":
    main()
