#!/usr/bin/env python3
"""Honest 10/day KPI: Buffer deliveries, approved backlog, provider and quota health.

Read only: never schedules or publishes a video and never reveals API keys.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from autofill_catalog import github
from buffer_autopublish import verify_channel
from ten_daily_slots import LOCAL_TIMES
from story_reserve import RESERVE_CAPACITY, remaining as reserve_remaining
from rolling_batches import progress as rolling_progress, STATE_PATH as ROLLING_PATH

HERE = Path(__file__).resolve().parent
TARGET = 10


def summarize(catalog, saved_ids, dispatched_ids, scheduled, sent, now, model=False,
              pexels=False, rolling_state=None, errored_posts=None, sending_posts=None):
    tz = ZoneInfo("Europe/Moscow")
    today = now.astimezone(tz).date()
    def today_only(rows, timestamp_field="dueAt"):
        results = []
        for p in rows:
            raw = p.get(timestamp_field) or p.get("dueAt")
            if not raw:
                continue
            when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if when.astimezone(tz).date() == today:
                results.append(p)
        return results
    sent_today = today_only(sent, timestamp_field="sentAt")
    scheduled_today = today_only(scheduled)
    new = [e for e in catalog["episodes"] if e.get("auto_preview") is True
           and e["id"] not in saved_ids]
    bank = json.loads((HERE / "seed_backlog.json").read_text("utf8"))
    named = {e["id"] for e in catalog["episodes"]}
    waiting = [e["id"] for e in bank["episodes"] if e["id"] not in named]
    deficits = []
    errored_posts = errored_posts or []
    sending_posts = sending_posts or []
    if errored_posts:
        deficits.append("BUFFER_YOUTUBE_DELIVERY_ERRORS: " + str(len(errored_posts)))
    if sending_posts:
        deficits.append("BUFFER_YOUTUBE_POSTS_STILL_SENDING: " + str(len(sending_posts)))
    pool = json.loads((HERE / "verified_pexels_pool.json").read_text("utf8"))
    used_footage = {src["source_page"] for ep in catalog["episodes"]
                    for src in ep.get("footage", []) if "source_page" in src}
    unused_public_clips = sum(src["source_page"] not in used_footage
                              for src in pool["sources"])
    # Script prompts can be composed locally; licensed moving footage cannot.
    if not pexels and unused_public_clips < 2 and not waiting:
        deficits.append("LICENSED_VIDEO_SUPPLY_LOW: public reserve exhausted; Commons may be limited")
    reserve_left = reserve_remaining(e.get("story_reserve_id") for e in catalog["episodes"])
    if reserve_left < 10000:
        deficits.append("EDITORIAL_STORY_RESERVE_LOW: expand template axes")
    if len(sent_today) + len(scheduled_today) < TARGET:
        deficits.append("BELOW_TEN_SCHEDULED_OR_SENT_TODAY")
    rolling = rolling_progress(rolling_state, len(scheduled)) if rolling_state else None
    return {
        "rolling_ten": rolling,
        "date_moscow": str(today), "daily_target": TARGET,
        "published_today_reported_by_buffer": len(sent_today),
        "scheduled_for_today": len(scheduled_today),
        "total_in_buffer_queue": len(scheduled),
        "buffer_delivery_error_count": len(errored_posts),
        "buffer_sending_count": len(sending_posts),
        "buffer_delivery_error_post_ids": [p.get("id") for p in errored_posts],
        "buffer_sending_post_ids": [p.get("id") for p in sending_posts],
        "new_unique_scripts_ready_to_render": len(new),
        "curated_unused_script_reserve": len(waiting),
        "accepted_buffer_receipts_all_time": len(dispatched_ids),
        "original_script_model_available": model,
        "keyless_editorial_script_reserve": True,
        "script_reserve_capacity": RESERVE_CAPACITY,
        "script_reserve_remaining": reserve_left,
        "script_reserve_type": "on_demand_narrative_variants_not_ready_mp4",
        "unconsumed_curated_pexels_clips": unused_public_clips,
        "pexels_search_key_available": pexels,
        "alternate_cc0_library": "limited, license verified live",
        "posting_windows_moscow": ["%02d:%02d" % x for x in LOCAL_TIMES],
        "hard_blockers": deficits,
    }


def main():
    now = datetime.now(timezone.utc)
    catalog = json.loads((HERE / "episodes.json").read_text("utf8"))
    tree = github("GET", "git/trees/render-ledger?recursive=1")
    if tree.get("truncated"):
        raise RuntimeError("Unable to confirm unique used footage inventory")
    saved = {Path(x["path"]).stem for x in tree.get("tree", [])
             if x["path"].startswith("render-receipts/")
             and x["path"].endswith(".json")}
    dispatched = {Path(x["path"]).stem for x in tree.get("tree", [])
                  if x["path"].startswith("buffer-publication-receipts/")
                  and x["path"].endswith(".json")}
    queued, sent, errors, sending = verify_channel(include_sent=True, include_errors=True)
    model = bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY"))
    pexels = bool(os.getenv("PEXELS_API_KEY"))
    import base64
    import preview_queue as ledger
    checkpoint = ledger.api(ROLLING_PATH)
    rolling_state = None
    if checkpoint:
        rolling_state = json.loads(base64.b64decode(
            "".join(checkpoint["content"].split()), validate=True))
    state = summarize(catalog, saved, dispatched, queued, sent, now,
                      model, pexels, rolling_state, errors, sending)
    print("GUSTAVA_TEN_A_DAY_STATUS", json.dumps(state, ensure_ascii=False))
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if path:
        lines = [
            "## GUSTAVA Enduro — ежедневные 10 Shorts",
            "",
            "| Метрика | Текущее значение |",
            "|---|---|",
            f"| Дата (Москва) | {state['date_moscow']} |",
            f"| Реально отправлено Buffer сегодня | {state['published_today_reported_by_buffer']} / 10 |",
            f"| Ещё запланировано на сегодня | {state['scheduled_for_today']} |",
            f"| Всего в очереди Buffer | {state['total_in_buffer_queue']} |",
            f"| Buffer: ошибка отправки в YouTube | {state['buffer_delivery_error_count']} |",
            f"| Buffer: зависшие отправки | {state['buffer_sending_count']} |",
            f"| Новых сценариев без render receipt | {state['new_unique_scripts_ready_to_render']} |",
            f"| Осталось оригиналов из резервного каталога | {state['curated_unused_script_reserve']} |",
            f"| Ключ модели для новых сценариев | {'YES' if model else 'NO'} |",
            f"| Ключ Pexels | {'YES' if pexels else 'NO (public reserve)'} |",
            f"| Неиспользованных проверенных публичных видео | {state['unconsumed_curated_pexels_clips']} |",
            "| Генерация сценариев без API-ключа | YES (offline editorial reserve) |",
            f"| Адресуемых вариантов сценариев | {state['script_reserve_capacity']:,} |",
            f"| Неиспользованных вариантов сценариев | {state['script_reserve_remaining']:,} |",
            "| Примечание | Сценарные варианты не равны готовым MP4 или лицензированным кадрам |",
            f"| Подтверждено Buffer status=sent с запуска контроля | {state['rolling_ten']['verified_buffer_sent_count_since_bootstrap'] if state['rolling_ten'] else 'не инициализировано'} |",
            f"| Прогресс текущей десятки | {state['rolling_ten']['current_pack_progress'] if state['rolling_ten'] else '—'}/10 |",
            f"| Следующая десятка сценариев подготовлена | {state['rolling_ten']['next_script_drafts_ready'] if state['rolling_ten'] else 0}/10 |",
            "",
            "### Ограничения",
        ] + ["- " + x for x in state["hard_blockers"]] + [
            "", "Все публикации проходят оригинальность, лицензию, ASR и motion QA.",
            "Зелёный workflow — не доказательство 10 опубликованных видеороликов.",
        ]
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf8")
    return state


if __name__ == "__main__":
    main()
