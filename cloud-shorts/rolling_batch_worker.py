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
from production_readiness import inventory, production_unavailable

MIN_REFILL_COOLDOWN_MINUTES = 45
MIN_BUFFER_SCHEDULED = 7  # alert if actual scheduled posts fall below this
REFILL_AT_OR_BELOW_SCHEDULED = 9  # owner contract: request next 10 at 9 remaining

REVIEWED_MP4_RESERVE_TARGET = 10
LOW_QUEUE_VOICE_REFILL_BELOW = 2  # 0-1 scheduled posts, never at 2
VOICE_REFILL_COOLDOWN_MINUTES = 30  # protect Actions and voice API from loops


def count_unqueued_reviewed_mp4(catalog, receipts, artifacts, ledger_paths):
    """Conservatively count distinct, unqueued MP4s with real QA evidence.

    Only an individually reviewed, SHA-pinned release whose original artifact
    still exists and whose original Deep/mixed QA receipt passes counts.
    Scripts and private/unreviewed previews are never a finished reserve.
    """
    import re
    from find_pending_publication import select as select_publishable

    paths = set(ledger_paths)
    blocked = {Path(p).stem for p in paths
               if (p.startswith("publication-receipts/")
                   or p.startswith("buffer-publication-receipts/"))
               and p.endswith(".json")}
    receipt_by_id = {}
    for record in receipts:
        slug = record.get("id")
        if slug in receipt_by_id:
            raise RuntimeError("Duplicate render receipts in reserve inventory")
        receipt_by_id[slug] = record

    eligible_episodes = []
    eligible_receipts = []
    for ep in catalog.get("episodes", []):
        slug = ep["id"]
        run = str(ep.get("reviewed_artifact_run_id") or "")
        sha = ep.get("reviewed_mp4_sha256") or ""
        if (slug in blocked or ep.get("auto_publish") is not True
                or not re.fullmatch(r"[0-9a-f]{64}", sha)
                or not run.isdigit()
                or "render-receipts/" + slug + ".json" not in paths):
            continue
        receipt = receipt_by_id.get(slug)
        if not receipt or str(receipt.get("run_id")) != run:
            continue
        eligible_episodes.append(ep)
        eligible_receipts.append(receipt)

    # Reuse the exact public release gate; never loosen voice/visual QA
    # merely to make the reserve dashboard show ten.
    eligible_catalog = {"episodes": eligible_episodes}
    count = 0
    while True:
        chosen = select_publishable(
            eligible_catalog, eligible_receipts, blocked, artifacts)
        if chosen is None:
            break
        blocked.add(chosen[1])
        count += 1
    return count


def live_unqueued_reviewed_mp4(catalog, include_reserved=False):
    """Fetch permanent publication receipts and active GitHub MP4 artifacts."""
    tree = github("GET", "git/trees/render-ledger?recursive=1")
    if tree.get("truncated"):
        raise RuntimeError("Incomplete MP4 receipt inventory; cannot count reserve")
    paths = [row["path"] for row in tree.get("tree", [])
             if row.get("type") == "blob"]
    published = {Path(p).stem for p in paths
                 if (p.startswith("publication-receipts/")
                     or p.startswith("buffer-publication-receipts/"))
                 and p.endswith(".json")}
    reserved_ids = {Path(row["path"]).stem for row in tree.get("tree", [])
                    if row.get("type") == "blob"
                    and row["path"].startswith("render-receipts/")
                    and row["path"].endswith(".json")}
    candidates = [ep for ep in catalog.get("episodes", [])
                  if ep.get("auto_publish") is True
                  and ep["id"] not in published
                  and "render-receipts/" + ep["id"] + ".json" in paths
                  and ep.get("reviewed_mp4_sha256")
                  and ep.get("reviewed_artifact_run_id")]
    if not candidates:
        return (0, reserved_ids) if include_reserved else 0
    receipts = []
    for ep in candidates:
        entry = ledger.api("render-receipts/" + ep["id"] + ".json")
        if not entry:
            raise RuntimeError("Missing permanent render receipt")
        receipts.append(ledger.decode_receipt(entry))
    artifacts = []
    for page in range(1, 7):
        response = github("GET", "actions/artifacts?per_page=100&page=" + str(page))
        artifacts.extend(response.get("artifacts", []))
        if len(response.get("artifacts", [])) < 100:
            break
    else:
        raise RuntimeError("Artifact list incomplete; cannot count QA reserve")
    count = count_unqueued_reviewed_mp4(catalog, receipts, artifacts, paths)
    return (count, reserved_ids) if include_reserved else count


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

def should_replenish(state, events, scheduled_count, now,
                     reviewed_mp4_reserve_count=REVIEWED_MP4_RESERVE_TARGET):
    if any(x in events for x in ("bootstrap_active_ten", "stage_next_ten",
                               "late_stage_ten", "promote_next_ten")):
        return True
    # This is the 9-post REPLENISH trigger, not the separate 7-post
    # low-stock alarm. Script creation and ready-to-send MP4s remain distinct.
    if (scheduled_count > REFILL_AT_OR_BELOW_SCHEDULED
            and reviewed_mp4_reserve_count >= REVIEWED_MP4_RESERVE_TARGET):
        return False
    last = iso(state.get("last_replenish_request_at"))
    return last is None or now - last >= timedelta(minutes=MIN_REFILL_COOLDOWN_MINUTES)

def should_request_voice_refill(state, scheduled_count, now):
    """Emergency voice+video production request, NOT proof of a ready WAV.

    The normal 9-post replenishment and 10 QA-MP4 reserve stay intact.
    An independent cooldown prevents a 0-post queue from dispatching
    indefinitely after a failed provider run or workflow_run event.
    """
    if scheduled_count < 0:
        raise ValueError("NEGATIVE_BUFFER_SCHEDULED_COUNT")
    if scheduled_count >= LOW_QUEUE_VOICE_REFILL_BELOW:
        return False
    last = iso(state.get("last_voice_refill_request_at"))
    return last is None or now - last >= timedelta(minutes=VOICE_REFILL_COOLDOWN_MINUTES)


def dispatch_plan(refill, urgent_voice_refill, events, scheduled_count,
                  ready_voice_candidates, reserve_count):
    """Pure action planner. Never dispatch an empty video/voice queue.

    Production requests are NOT successful clips or Buffer receipts. This
    scheduler can be regression-tested without talking to external services.
    """
    if min(scheduled_count, ready_voice_candidates, reserve_count) < 0:
        raise ValueError("NEGATIVE_FACTORY_INVENTORY")
    source = bool(refill or urgent_voice_refill)
    shortage = bool(urgent_voice_refill
                    or (refill and scheduled_count < MIN_BUFFER_SCHEDULED))
    return {
        "request_new_sources":source,
        "request_voice_and_render":bool(shortage and ready_voice_candidates > 0),
        "request_verified_buffer_delivery":bool(
            reserve_count > 0 and
            ("promote_next_ten" in events or
             (refill and scheduled_count < MIN_BUFFER_SCHEDULED))),
        "voice_not_ready":bool(shortage and ready_voice_candidates == 0),
        "no_qa_mp4_for_buffer":bool(scheduled_count < MIN_BUFFER_SCHEDULED
                                   and reserve_count == 0),
    }


def factory_health(scheduled_count,reserve_count,voice_count,routes):
    blockers=[]
    if not routes: blockers.append("NO_CONNECTED_TTS_ENDPOINT")
    if voice_count==0: blockers.append("NO_VOICE_READY_EPISODES")
    if reserve_count==0: blockers.append("NO_REVIEWED_MP4_STOCK")
    if scheduled_count==0: blockers.append("BUFFER_QUEUE_EMPTY")
    return {"operational":not blockers,"status":"BLOCKED" if blockers else
            "SUPPLY_PRESENT_NOT_PUBLICATION_PROOF","blockers":blockers,
            "youtube_publications_verified":None}


def needs_persist(before, after, events, now):
    if before is None or events:
        return True
    for key in ("verified_sent_count", "next_cursor", "last_replenish_request_at",
                "last_voice_refill_request_at"):
        if before.get(key) != after.get(key):
            return True
    last = iso(before.get("last_polled_at"))
    return last is None or now - last >= timedelta(hours=6)

def main():
    if os.getenv("GITHUB_REPOSITORY") != "GUSTAVA009/moto-shorts-cloud":
        raise RuntimeError("Wrong repository for rolling ten")
    scheduled, sent, errors, sending = verify_channel(include_sent=True, include_errors=True)
    if errors:
        print('::warning::BUFFER_DELIVERY_ERRORS: ' + str(len(errors)) + ' failed uploads; do not double-submit', flush=True)
    if sending:
        print('::warning::BUFFER_STUCK_SENDING: ' + str(len(sending)) + ' pending uploads; no blind retries', flush=True)
    entry = ledger.api(STATE_PATH)
    before = read_state(entry)
    catalog_entry = github("GET", "contents/cloud-shorts/episodes.json?ref=main")
    catalog = json.loads(base64.b64decode(catalog_entry["content"]))
    used_ids = [e["story_reserve_id"] for e in catalog["episodes"] if e.get("story_reserve_id")]
    titles = [e["title"] for e in catalog["episodes"]]
    now = datetime.now(timezone.utc)
    state, events = reconcile(before, sent, now=now.isoformat(),
                              consumed_ids=used_ids, consumed_titles=titles)
    reserve_count, reserved_ids = live_unqueued_reviewed_mp4(
        catalog, include_reserved=True)
    voice_supply = inventory(catalog, reserved_ids)
    # A script is not voice-ready merely because a cron requests a render.
    # Block speculative renders if there is neither a pinned historic Deep
    # audio source nor an owner-configured private voice route.
    ready_voice_candidates = voice_supply["ready_unattended_voice_episodes"]
    refill = should_replenish(state, events, len(scheduled), now,
                              reviewed_mp4_reserve_count=reserve_count)
    urgent_voice_refill = should_request_voice_refill(state, len(scheduled), now)
    if refill:
        state["last_replenish_request_at"] = now.isoformat()
    if urgent_voice_refill:
        state["last_voice_refill_request_at"] = now.isoformat()
    if needs_persist(before, state, events, now):
        ledger.store(STATE_PATH, state,
                     "Rolling ten verified sent checkpoint: "+(", ".join(events) or "poll"),
                     old_sha=entry["sha"] if entry else None)
    summary = {"events":events, "dispatch_replenishment":refill,
               "low_queue_voice_and_render_requested":urgent_voice_refill,
               "low_queue_voice_trigger_below":LOW_QUEUE_VOICE_REFILL_BELOW,
               "unqueued_reviewed_mp4_reserve":reserve_count,
               "unqueued_reviewed_mp4_target":REVIEWED_MP4_RESERVE_TARGET,
               "voice_ready_unrendered_episodes":ready_voice_candidates,
               "configured_owner_voice_routes":voice_supply["configured_voice_route_names"],
               "voice_live_verified":voice_supply["voice_route_reachability_verified"],
               "unrendered_scripts_needing_voice":(
                   voice_supply["unrendered_missing_original_deep"]
                   +voice_supply["unrendered_selfhosted_not_configured"]),
               "buffer_delivery_errors":len(errors), "buffer_still_sending":len(sending),
               **progress(state, len(scheduled))}
    plan = dispatch_plan(refill, urgent_voice_refill, events, len(scheduled),
                         ready_voice_candidates, reserve_count)
    summary["actions"] = plan
    summary["factory_health"] = factory_health(
        len(scheduled),reserve_count,ready_voice_candidates,
        voice_supply["configured_voice_route_names"])
    print("ROLLING_TEN_STATUS",json.dumps(summary,ensure_ascii=False),flush=True)
    if not summary["factory_health"]["operational"]:
        print("::error::FACTORY_NOT_OPERATIONAL: "+
              ",".join(summary["factory_health"]["blockers"]),flush=True)
    if plan["request_new_sources"]:
        github("POST","actions/workflows/autofill-motorcycle.yml/dispatches",{"ref":"main"})
        print("ROLLING_TEN_AUTOFILL_DISPATCHED",flush=True)
    if plan["request_voice_and_render"]:
        github("POST","actions/workflows/daily-preview.yml/dispatches",{"ref":"main"})
        print("ROLLING_TEN_VOICE_READY_PREVIEW_DISPATCHED", ready_voice_candidates,
              flush=True)
    elif plan["voice_not_ready"]:
        print("::warning::VOICE_SUPPLY_BLOCKED: only unvoiced scripts remain; "
              "no manual Deep generation. Cloud, Windows or approved independent "
              "third owner TTS must provide an actual SHA-pinned WAV.",flush=True)
    if plan["request_verified_buffer_delivery"]:
        github("POST","actions/workflows/buffer-backlog.yml/dispatches",{"ref":"main"})
        print("ROLLING_TEN_VERIFIED_PUBLISHER_DISPATCHED",flush=True)
    elif plan["no_qa_mp4_for_buffer"]:
        print("::warning::MP4_SUPPLY_BLOCKED: zero released, QA-reviewed MP4 "
              "available; do not falsely report Buffer replenished.",flush=True)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        lines=["## Rolling ten: Buffer status=sent", "",
               "Confirmed sent since bootstrap: "+str(summary["verified_buffer_sent_count_since_bootstrap"]),
               "Current batch: "+str(summary["current_pack_progress"])+"/10",
               "Active draft scripts: "+str(summary["active_script_drafts_ready"]),
               "Next staged draft scripts: "+str(summary["next_script_drafts_ready"]),
               "Scheduled in Buffer: "+str(summary["buffer_scheduled_posts"]),
               "Separate release-eligible QA MP4 reserve: "+str(reserve_count)+"/10", "",
               "Drafts are not QA-passed MP4s or verified public YouTube views."]
        lines.extend(["Factory health: "+summary["factory_health"]["status"],
                      "Blockers: "+(", ".join(summary["factory_health"]["blockers"]) or "none"),
                      "Workflow success is NOT proof of YouTube publication."])
        Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text("\n".join(lines)+"\n",encoding="utf8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
