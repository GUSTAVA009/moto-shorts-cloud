#!/usr/bin/env python3
"""GitHub Actions: roll batches by verified Buffer status=sent, never scheduled."""
from __future__ import annotations
import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from autofill_catalog import github
from buffer_autopublish import verify_channel
import preview_queue as ledger
from rolling_batches import STATE_PATH, reconcile, progress

MIN_REFILL_COOLDOWN_MINUTES = 45
MIN_BUFFER_SCHEDULED = 3

def read_state(entry):
    if not entry:
        return None
    if not entry.get("sha") or not entry.get("content"):
        raise RuntimeError("Rolling ten state incomplete; refusing to reset post history")
    try:
        return json.loads(base64.b64decode("".join(entry["content"].split()), validate=True))
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Rolling ten state corrupt; refusing to erase history") from exc

def iso(text):
    if not text:
        return None
    value = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Rolling ten timestamp missing timezone")
    return value

def should_replenish(state, events, scheduled_count, now):
    if any(x in events for x in ("bootstrap_active_ten", "stage_next_ten",
                               "late_stage_ten", "promote_next_ten")):
        return True
    if scheduled_count >= MIN_BUFFER_SCHEDULED:
        return False
    last = iso(state.get("last_replenish_request_at"))
    return last is None or now - last >= timedelta(minutes=MIN_REFILL_COOLDOWN_MINUTES)

def needs_persist(before, after, events, now):
    if before is None or events:
        return True
    for key in ("verified_sent_count", "next_cursor", "last_replenish_request_at"):
        if before.get(key) != after.get(key):
            return True
    last = iso(before.get("last_polled_at"))
    return last is None or now - last >= timedelta(hours=6)

def main():
    if os.getenv("GITHUB_REPOSITORY") != "GUSTAVA009/moto-shorts-cloud":
        raise RuntimeError("Wrong repository for rolling ten")
    scheduled, sent = verify_channel(include_sent=True)
    entry = ledger.api(STATE_PATH)
    before = read_state(entry)
    catalog_entry = github("GET", "contents/cloud-shorts/episodes.json?ref=main")
    catalog = json.loads(base64.b64decode(catalog_entry["content"]))
    used_ids = [e["story_reserve_id"] for e in catalog["episodes"] if e.get("story_reserve_id")]
    titles = [e["title"] for e in catalog["episodes"]]
    now = datetime.now(timezone.utc)
    state, events = reconcile(before, sent, now=now.isoformat(),
                              consumed_ids=used_ids, consumed_titles=titles)
    refill = should_replenish(state, events, len(scheduled), now)
    if refill:
        state["last_replenish_request_at"] = now.isoformat()
    if needs_persist(before, state, events, now):
        ledger.store(STATE_PATH, state,
                     "Rolling ten verified sent checkpoint: "+(", ".join(events) or "poll"),
                     old_sha=entry["sha"] if entry else None)
    summary = {"events":events, "dispatch_replenishment":refill,
               **progress(state, len(scheduled))}
    print("ROLLING_TEN_STATUS",json.dumps(summary,ensure_ascii=False),flush=True)
    if refill:
        github("POST","actions/workflows/autofill-motorcycle.yml/dispatches",{"ref":"main"})
        print("ROLLING_TEN_AUTOFILL_DISPATCHED",flush=True)
    if refill and len(scheduled) < MIN_BUFFER_SCHEDULED:
        # When stock is queued in episodes.json but Buffer is running empty,
        # a new supplier run alone can be a no-op. Explicitly nudge the
        # guarded renderer and sender; both implement receipt deduplication.
        github("POST","actions/workflows/daily-preview.yml/dispatches",{"ref":"main"})
        print("ROLLING_TEN_URGENT_PREVIEW_DISPATCHED",flush=True)
    if "promote_next_ten" in events or (refill and len(scheduled) < MIN_BUFFER_SCHEDULED):
        github("POST","actions/workflows/buffer-backlog.yml/dispatches",{"ref":"main"})
        print("ROLLING_TEN_VERIFIED_PUBLISHER_DISPATCHED",flush=True)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        lines=["## Rolling ten: Buffer status=sent", "",
               "Confirmed sent since bootstrap: "+str(summary["verified_buffer_sent_count_since_bootstrap"]),
               "Current batch: "+str(summary["current_pack_progress"])+"/10",
               "Active draft scripts: "+str(summary["active_script_drafts_ready"]),
               "Next staged draft scripts: "+str(summary["next_script_drafts_ready"]),
               "Scheduled in Buffer: "+str(summary["buffer_scheduled_posts"]), "",
               "Drafts are not QA-passed MP4s or verified public YouTube views."]
        Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text("\n".join(lines)+"\n",encoding="utf8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
