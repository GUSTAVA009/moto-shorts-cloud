"""Owner's MINIMUM 400 finished unique Shorts/month production target.

Baseline is 14/day for 30-31 day months; 15/day for a 28-day February.
An observed monthly deficit can trigger a capped 16-per-day catch-up budget,
provided independent voice, footage, video and Buffer QA gates all pass.
No scripts, API responses or scheduled uploads count as confirmed deliveries.
"""
from __future__ import annotations
import calendar
from datetime import datetime, timezone
from math import ceil
from zoneinfo import ZoneInfo

MINIMUM_MONTHLY_SHORTS = 400
BASE_DAILY_SHORTS = 14
MAX_DAILY_CATCHUP_SHORTS = 16
MINS_BETWEEN_RELEASES = 90
TIMEZONE = "Europe/Moscow"


def _ts(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("MONTHLY_SENT_TIMESTAMP_MISSING")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError) as error:
        raise ValueError("MONTHLY_SENT_TIMESTAMP_INVALID") from error
    if dt.tzinfo is None:
        raise ValueError("MONTHLY_SENT_TIMESTAMP_NEEDS_TIMEZONE")
    return dt.astimezone(timezone.utc)


def month_capacity(now: datetime, seen_buffer_ids=None, recent_sent=None):
    """Observe distinct confirmed Buffer sentAt timestamps (not YouTube public).

    A missing/late ledger is NOT asserted as complete. Only unique Buffer sent
    status with real sentAt counts; this is not video review or proof of a
    public YouTube URL. The provider may not return the whole month's posts.
    """
    if now.tzinfo is None:
        raise ValueError("MONTHLY_REPORT_REQUIRES_TIMEZONE")
    local = now.astimezone(ZoneInfo(TIMEZONE))
    year, month = local.year, local.month
    days = calendar.monthrange(year, month)[1]
    rest = days - local.day + 1
    merged = {}
    for post_id, stamp in (seen_buffer_ids or {}).items():
        if not isinstance(post_id, str) or not post_id.strip():
            raise ValueError("MONTHLY_SENT_POST_ID_INVALID")
        merged[post_id] = _ts(stamp)
    for row in recent_sent or []:
        if not isinstance(row, dict) or not row.get("id") or not row.get("sentAt"):
            raise ValueError("MONTHLY_SENT_RECEIPT_UNVERIFIED")
        instant = _ts(row["sentAt"])
        post_id = row["id"]
        if post_id in merged and merged[post_id] != instant:
            raise ValueError("MONTHLY_SENT_RECEIPT_CONFLICT")
        merged[post_id] = instant
    inside = [(post_id, dt) for post_id, dt in merged.items()
              if (dt.astimezone(ZoneInfo(TIMEZONE)).year,
                  dt.astimezone(ZoneInfo(TIMEZONE)).month) == (year, month)]
    observed = len(inside)
    today = sum(dt.astimezone(ZoneInfo(TIMEZONE)).date() == local.date()
                for _, dt in inside)
    remaining = max(0, MINIMUM_MONTHLY_SHORTS - observed)
    # February needs 15/day; a fixed 14/day baseline misses 400 in 28 days.
    baseline = max(BASE_DAILY_SHORTS, ceil(MINIMUM_MONTHLY_SHORTS / days))
    necessary_daily = ceil(remaining / rest) if rest else remaining
    recommended = min(MAX_DAILY_CATCHUP_SHORTS,
                      max(baseline, necessary_daily))
    return {
        "month": f"{year}-{month:02d}",
        "days_in_month": days,
        "days_left_including_today": rest,
        "monthly_minimum": MINIMUM_MONTHLY_SHORTS,
        "baseline_daily_target": baseline,
        "max_catchup_daily": MAX_DAILY_CATCHUP_SHORTS,
        "minimum_baseline_monthly": days * baseline,
        "observed_buffer_sent_this_month": observed,
        "observed_buffer_sent_today": today,
        "not_yet_verified_against_monthly_minimum": remaining,
        "daily_catchup_goal": recommended,
        "necessary_per_day_without_cap": necessary_daily,
        "monthly_goal_achievable_at_current_capacity":
            remaining <= rest * MAX_DAILY_CATCHUP_SHORTS,
        "claims_complete_youtube_publication": False,
        "historical_ledger_completeness_verified": False,
        "monthly_minimum_confirmed_from_observed_receipts":
            observed >= MINIMUM_MONTHLY_SHORTS,
        "notes": "Only distinct Buffer status=sent with sentAt counted; "
                 "YouTube-public URL receipts and MP4 QA verified separately."
    }
