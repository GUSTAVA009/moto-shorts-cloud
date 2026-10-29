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

HERE = Path(__file__).resolve().parent
TARGET = 10


def summarize(catalog, saved_ids, dispatched_ids, scheduled, sent, now, model=False,
              pexels=False):
    tz = ZoneInfo("Europe/Moscow")
    today = now.astimezone(tz).date()
    def today_only(rows):
        results = []
        for p in rows:
            raw = p.get("dueAt")
            if not raw:
                continue
            when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if when.astimezone(tz).date() == today:
                results.append(p)
        return results
    sent_today = today_only(sent)
    scheduled_today = today_only(scheduled)
    new = [e for e in catalog["episodes"] if e.get("auto_preview") is True
           and e["id"] not in saved_ids]
    bank = json.loads((HERE / "seed_backlog.json").read_text("utf8"))
    named = {e["id"] for e in catalog["episodes"]}
    waiting = [e["id"] for e in bank["episodes"] if e["id"] not in named]
    deficits = []
    if not model and not waiting:
        deficits.append("NO_ORIGINAL_STORY_MODEL_AND_CURATED_BACKLOG_EXHAUSTED")
    if not pexels:
        deficits.append("PEXELS_API_KEY_NOT_CONFIGURED: CC0 fallback limited")
    if len(sent_today) + len(scheduled_today) < TARGET:
        deficits.append("BELOW_TEN_SCHEDULED_OR_SENT_TODAY")
    return {
        "date_moscow": str(today), "daily_target": TARGET,
        "published_today_reported_by_buffer": len(sent_today),
        "scheduled_for_today": len(scheduled_today),
        "total_in_buffer_queue": len(scheduled),
        "new_unique_scripts_ready_to_render": len(new),
        "curated_unused_script_reserve": len(waiting),
        "accepted_buffer_receipts_all_time": len(dispatched_ids),
        "original_script_model_available": model,
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
    queued, sent = verify_channel(include_sent=True)
    model = bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY"))
    pexels = bool(os.getenv("PEXELS_API_KEY"))
    state = summarize(catalog, saved, dispatched, queued, sent, now, model, pexels)
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
            f"| Новых сценариев без render receipt | {state['new_unique_scripts_ready_to_render']} |",
            f"| Осталось оригиналов из резервного каталога | {state['curated_unused_script_reserve']} |",
            f"| Ключ модели для новых сценариев | {'YES' if model else 'NO'} |",
            f"| Ключ Pexels | {'YES' if pexels else 'NO'} |",
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
