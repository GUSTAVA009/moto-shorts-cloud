#!/usr/bin/env python3
"""Honest >=330/month KPI: sent Buffer receipts, ready MP4s and source bottlenecks.

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
from deep_voice import ready as deep_ready, VOICE_ENGINE as DEEP_ENGINE
from voice_routing import ready as allowed_voice_ready
from selfhosted_voice import VOICE_ENGINE as OWNER_CPU_ENGINE
from monthly_capacity import month_capacity, BASE_DAILY_SHORTS, MINIMUM_MONTHLY_SHORTS
from visual_director import verify_story_subject
from ten_daily_slots import LOCAL_TIMES
from story_reserve import RESERVE_CAPACITY, remaining as reserve_remaining
from rolling_batches import progress as rolling_progress, STATE_PATH as ROLLING_PATH

HERE = Path(__file__).resolve().parent
TARGET = BASE_DAILY_SHORTS


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
    # Script count is NOT production capacity. A new episode needs the real
    # voice_id=deep asset and subject-matching footage, not just a scenario.
    real_deep_ready = [e for e in new if deep_ready(e)]
    real_owner_cpu_ready = [e for e in new if e.get("voice_engine")==OWNER_CPU_ENGINE
                            and allowed_voice_ready(e)]
    # Do not claim a script is an MP4 even after its audio and scene preflight.
    visually_eligible = []
    visually_rejected = []
    for e in real_deep_ready + real_owner_cpu_ready:
        try:
            verify_story_subject(e)
            visually_eligible.append(e)
        except ValueError:
            visually_rejected.append(e)
    waiting_deep_audio = [e for e in new if e.get("voice_engine")==DEEP_ENGINE
                          and not deep_ready(e)]
    waiting_owner_cpu = [e for e in new if e.get("voice_engine")==OWNER_CPU_ENGINE
                         and not allowed_voice_ready(e)]
    monthly = month_capacity(
        now, (rolling_state or {}).get("seen_buffer_sent_ids", {}), sent)
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
    # Source_story requires TWO distinct fresh, verifiably matching actions
    # by two different filmmakers per original episode. At a twelve-day pace,
    # 24 novel approved clips/day and 168/week are needed. These are planning
    # estimates, NOT a claim that the public pool contains usable actions.
    minimum_distinct_new_clips_daily = TARGET * 2
    weekly_clip_floor = minimum_distinct_new_clips_daily * 7
    verified_clip_days = unused_public_clips // minimum_distinct_new_clips_daily
    # Script prompts can be composed locally; licensed moving footage cannot.
    if not pexels and unused_public_clips < weekly_clip_floor:
        deficits.append(
            "LICENSED_ACTION_MATCHED_FOOTAGE_BELOW_330_MONTH_PACE: "
            + str(unused_public_clips) + " unused public source IDs vs "
            + str(weekly_clip_floor) + " new clips for 7-day buffer; "
            "filmmaker identity, action and license still need live verification"
        )
    reserve_left = reserve_remaining(e.get("story_reserve_id") for e in catalog["episodes"])
    if reserve_left < 10000:
        deficits.append("EDITORIAL_STORY_RESERVE_LOW: expand template axes")
    if len(sent_today) + len(scheduled_today) < TARGET:
        deficits.append("BELOW_TWELVE_SCHEDULED_OR_SENT_TODAY")
    if len(visually_eligible) < max(0,TARGET-len(sent_today)-len(scheduled_today)):
        deficits.append("NOT_ENOUGH_APPROVED_ORIGINAL_VOICE_AND_VISUAL_STOCK_FOR_TWELVE")
    if waiting_deep_audio:
        deficits.append("DEEP_AUDIO_STOCK_MISSING: "+str(len(waiting_deep_audio)))
    if waiting_owner_cpu:
        deficits.append("CLOUD_OWNER_QWEN_AUDIO_NOT_CONNECTED: "+str(len(waiting_owner_cpu)))
    if not monthly["monthly_goal_achievable_at_current_capacity"]:
        deficits.append("MONTHLY_330_TARGET_NOT_RECOVERABLE_WITH_16_DAILY_WINDOWS")
    if visually_rejected:
        deficits.append("VISUAL_TOPIC_MISMATCH: "+str(len(visually_rejected)))
    # No verified public API exists for unattended AI Doc Maker Deep TTS.
    # ChatGPT scheduled task has been created, but actual execution and
    # provider quota must be confirmed separately; never imply it ran.
    if len(sent_today)<TARGET:
        deficits.append("TWELVE_PUBLISHED_TODAY_NOT_CONFIRMED")
    rolling = rolling_progress(rolling_state, len(scheduled)) if rolling_state else None
    return {
        "rolling_ten": rolling,
        "monthly_minimum_short": MINIMUM_MONTHLY_SHORTS,
        "monthly_delivery_observations": monthly,
        "monthly_minimum_observed_from_buffer_sent": monthly["monthly_minimum_confirmed_from_observed_receipts"],
        "date_moscow": str(today), "daily_target": TARGET,
        "published_today_reported_by_buffer": len(sent_today),
        "scheduled_for_today": len(scheduled_today),
        "total_in_buffer_queue": len(scheduled),
        "buffer_delivery_error_count": len(errored_posts),
        "buffer_sending_count": len(sending_posts),
        "buffer_delivery_error_post_ids": [p.get("id") for p in errored_posts],
        "buffer_sending_post_ids": [p.get("id") for p in sending_posts],
        "new_unique_scripts_ready_to_render": len(new),
        "new_true_deep_audio_assets_ready": len(real_deep_ready),
        "new_owner_cloud_cpu_api_candidates": len(real_owner_cpu_ready),
        "new_owner_cloud_cpu_api_not_connected": len(waiting_owner_cpu),
        "new_deep_visuals_and_voice_both_verified": len(visually_eligible),
        "new_deep_voice_assets_missing": len(waiting_deep_audio),
        "new_deep_visual_subject_rejections": len(visually_rejected),
        "true_twelve_sent_today_confirmed": len(sent_today)>=TARGET,
        "autonomous_deep_tts_api_confirmed": False,
        "cloud_selfhosted_voice_server_live_confirmed": False,
        "curated_unused_script_reserve": len(waiting),
        "accepted_buffer_receipts_all_time": len(dispatched_ids),
        "original_script_model_available": model,
        "keyless_editorial_script_reserve": True,
        "script_reserve_capacity": RESERVE_CAPACITY,
        "script_reserve_remaining": reserve_left,
        "script_reserve_type": "on_demand_narrative_variants_not_ready_mp4",
        "unconsumed_curated_pexels_clips": unused_public_clips,
        "minimum_new_distinct_action_clips_per_day": minimum_distinct_new_clips_daily,
        "minimum_seven_day_source_buffer_clips": weekly_clip_floor,
        "public_footage_source_id_coverage_days_upper_bound": verified_clip_days,
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
    print("GUSTAVA_MIN_330_MONTH_STATUS", json.dumps(state, ensure_ascii=False))
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if path:
        lines = [
            "## GUSTAVA Enduro — минимум 330 Shorts / месяц",
            "",
            "| Метрика | Текущее значение |",
            "|---|---|",
            f"| Дата (Москва) | {state['date_moscow']} |",
            f"| Реально отправлено Buffer сегодня | {state['published_today_reported_by_buffer']} / 12 |",
            f"| Минимум в месяц | {state['monthly_minimum_short']} |",
            f"| Наблюдалось Buffer sent в текущем месяце | {state['monthly_delivery_observations']['observed_buffer_sent_this_month']} |",
            f"| Требуемо сегодня с учётом отставания | {state['monthly_delivery_observations']['daily_catchup_goal']} |",
            f"| Можно догнать к концу месяца при 16/сутки | {state['monthly_delivery_observations']['monthly_goal_achievable_at_current_capacity']} |",
            f"| Ещё запланировано на сегодня | {state['scheduled_for_today']} |",
            f"| Всего в очереди Buffer | {state['total_in_buffer_queue']} |",
            f"| Buffer: ошибка отправки в YouTube | {state['buffer_delivery_error_count']} |",
            f"| Buffer: зависшие отправки | {state['buffer_sending_count']} |",
            f"| Новых сценариев без render receipt | {state['new_unique_scripts_ready_to_render']} |",
            f"| Подтверждённых DEEP MP3, ещё не отрендеренных | {state['new_true_deep_audio_assets_ready']} |",
            f"| Deep + тематически подходящее видео | {state['new_deep_visuals_and_voice_both_verified']} |",
            f"| Не хватает оригинальных DEEP-записей | {state['new_deep_voice_assets_missing']} |",
            f"| Отклонено за несоответствие сюжета кадрам | {state['new_deep_visual_subject_rejections']} |",
            f"| 12 Buffer sent сегодня | {'ДА' if state['true_twelve_sent_today_confirmed'] else 'НЕТ'} |",
            f"| Подтверждён официальный API DEEP | НЕТ (автоматизация ChatGPT требует проверки) |",
            f"| Осталось оригиналов из резервного каталога | {state['curated_unused_script_reserve']} |",
            f"| Ключ модели для новых сценариев | {'YES' if model else 'NO'} |",
            f"| Ключ Pexels | {'YES' if pexels else 'NO (public reserve)'} |",
            f"| Неиспользованных проверенных публичных видео | {state['unconsumed_curated_pexels_clips']} |",
            f"| Минимально свежих сюжетных клипов / день | {state['minimum_new_distinct_action_clips_per_day']} |",
            f"| Запас сюжетных клипов на 7 дней | {state['minimum_seven_day_source_buffer_clips']} |",
            f"| Верхняя оценка дней запаса по ID | {state['public_footage_source_id_coverage_days_upper_bound']} |",
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
