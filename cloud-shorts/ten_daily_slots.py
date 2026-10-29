"""Ten daily release windows for verified original GUSTAVA Enduro Shorts.

Buffer's public GraphQL API supports per-post customScheduled/dueAt; it does
not expose the legacy recurring posting-schedule editor. We choose exact
per-post slots, independent of the old 14-slots-per-week channel queue.
No extra or repeated content is generated here.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo

TARGET_PER_DAY = 10
TZ_NAME = "Europe/Moscow"
LOCAL_TIMES = ((8, 25), (10, 0), (11, 35), (13, 10), (14, 45),
               (16, 20), (17, 55), (19, 30), (21, 5), (22, 40))
MIN_LEAD_MINUTES = 8
MIN_SPACING_MINUTES = 45


def parse_date(value):
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("Invalid existing Buffer dueAt: refusing unsafe slot reuse")
    if dt.tzinfo is None:
        raise ValueError("Buffer timestamp missing timezone")
    return dt.astimezone(timezone.utc)


def choose_slot(posts, now=None, timezone_name=TZ_NAME):
    """Choose the next local daily slot, accounting for scheduled and sent posts.

    Does not modify a scheduled post, does not bypass post QA or duplicate checks.
    """
    tz = ZoneInfo(timezone_name)
    now = parse_date(now or datetime.now(timezone.utc))
    seen = []
    for post in posts:
        due = post.get("dueAt") if isinstance(post, dict) else post
        if due:
            seen.append(parse_date(due))
    start = now.astimezone(tz).date()
    for day in range(21):
        target_day = start + timedelta(days=day)
        day_posts = [p for p in seen if p.astimezone(tz).date() == target_day]
        if len(day_posts) >= TARGET_PER_DAY:
            continue
        for hour, minute in LOCAL_TIMES:
            local = datetime.combine(target_day, time(hour=hour, minute=minute), tzinfo=tz)
            candidate = local.astimezone(timezone.utc)
            if candidate <= now + timedelta(minutes=MIN_LEAD_MINUTES):
                continue
            if any(abs((candidate - other).total_seconds()) <
                   MIN_SPACING_MINUTES * 60 for other in seen):
                continue
            return candidate.isoformat(timespec="seconds").replace("+00:00", "Z")
    raise RuntimeError("NO_SAFE_BUFFER_SLOT: all upcoming days full or unavailable")
