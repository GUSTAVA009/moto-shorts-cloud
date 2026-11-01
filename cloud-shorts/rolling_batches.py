#!/usr/bin/env python3
"""Rolling 10-Short editorial batches, driven ONLY by verified Buffer sent posts.

A staged batch consists of ten *draft scripts*, not licensed footage,
QA-passed MP4s or proof of public YouTube visibility.
The saved GitHub render-ledger state is the idempotent source of truth.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
import hashlib

from story_reserve import at, RESERVE_CAPACITY, THEME_KEYS, PER_THEME

STATE_PATH = "automation/rolling-ten.json"
BATCH_SIZE = 10
VERSION = 1
STEP = 10001
assert __import__("math").gcd(STEP, RESERVE_CAPACITY) == 1


def fresh_state() -> dict:
    return {
        "version": VERSION, "verified_sent_count": 0,
        "seen_buffer_sent_ids": {}, "active_batch": None, "pending_batch": None,
        "next_cursor": 0, "last_polled_at": None,
        "last_replenish_request_at": None,
        "last_voice_refill_request_at": None,
        "notes": "Count is Buffer sent statuses observed since tracking/bootstrap; NOT lifetime YouTube published count.",
    }


def validate_state(state):
    if not isinstance(state, dict) or state.get("version") != VERSION:
        raise ValueError("Rolling story batch ledger missing expected version")
    if not isinstance(state.get("seen_buffer_sent_ids"), dict):
        raise ValueError("Corrupt sent post ledger")
    count = state.get("verified_sent_count")
    cursor = state.get("next_cursor")
    if type(count) is not int or count < 0:
        raise ValueError("Invalid verified publication count")
    if type(cursor) is not int or not 0 <= cursor <= RESERVE_CAPACITY:
        raise ValueError("Invalid scenario reserve cursor")
    for key in ("active_batch", "pending_batch"):
        obj = state.get(key)
        if obj is not None and (
            not isinstance(obj, dict)
            or not isinstance(obj.get("scripts"), list)
            or len(obj["scripts"]) != BATCH_SIZE
            or type(obj.get("number")) is not int
        ):
            raise ValueError("Invalid editorial script batch: " + key)
    return state


def make_batch(number, cursor, consumed_reserve_ids=(), consumed_titles=()):
    """Allocate ten distinct addresses, spread over different motorcycle themes."""
    if type(number) is not int or number < 0:
        raise ValueError("Invalid batch number")
    used_ids = set(consumed_reserve_ids)
    titles = {str(t).strip().casefold() for t in consumed_titles}
    scripts = []
    while len(scripts) < BATCH_SIZE:
        if cursor >= RESERVE_CAPACITY:
            raise RuntimeError("EDITORIAL_RESERVE_EXHAUSTED: cannot prepare another ten")
        index = (cursor * STEP) % RESERVE_CAPACITY
        cursor += 1
        draft = at(index)
        if draft["_reserve_id"] in used_ids or draft["title"].casefold() in titles:
            continue
        draft["theme"] = THEME_KEYS[index // PER_THEME]
        used_ids.add(draft["_reserve_id"])
        titles.add(draft["title"].casefold())
        scripts.append(draft)
    return {"number": number, "status": "draft_scripts_ready",
            "scripts": scripts, "size": len(scripts)}, cursor


def _normalize_sent(sent_posts):
    """Only Buffer's status=sent results with a real ID and sentAt count."""
    if not isinstance(sent_posts, list):
        raise ValueError("Buffer sent-post inventory must be a list")
    unique = {}
    for row in sent_posts:
        post_id = row.get("id") if isinstance(row, dict) else None
        timestamp = row.get("sentAt") if isinstance(row, dict) else None
        if not isinstance(post_id, str) or not post_id.strip() or not timestamp:
            raise ValueError("Incomplete Buffer sent post: status/time/id uncertain")
        try:
            instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if instant.tzinfo is None:
                raise ValueError("Buffer sent timestamp has no timezone")
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Buffer sent timestamp invalid") from exc
        if post_id in unique and unique[post_id] != timestamp:
            raise ValueError("Conflicting Buffer sent timestamps for one post")
        unique[post_id] = timestamp
    return sorted(unique.items(), key=lambda pair: (pair[1], pair[0]))


def reconcile(old_state, sent_posts, now=None, consumed_ids=(), consumed_titles=()):
    """Return next immutable snapshot and stage/promote events.

    9th/19th/29th *verified sent* post -> stage ten unique drafts.
    10th/20th/30th *verified sent* post -> promote those ten drafts.
    Rechecking same posts creates no new batch or extra event.
    """
    state = deepcopy(old_state) if old_state is not None else fresh_state()
    validate_state(state)
    stamp = now or datetime.now(timezone.utc).isoformat()
    events = []
    allocated_ids = set(consumed_ids)
    allocated_titles = {str(t).strip().casefold() for t in consumed_titles}
    for batch in (state["active_batch"], state["pending_batch"]):
        if batch:
            allocated_ids.update(s["_reserve_id"] for s in batch["scripts"])
            allocated_titles.update(s["title"].casefold() for s in batch["scripts"])

    if state["active_batch"] is None:
        batch, cursor = make_batch(
            0, state["next_cursor"], allocated_ids, allocated_titles)
        state["active_batch"] = batch
        state["next_cursor"] = cursor
        allocated_ids.update(s["_reserve_id"] for s in batch["scripts"])
        allocated_titles.update(s["title"].casefold() for s in batch["scripts"])
        events.append("bootstrap_active_ten")

    normalized = _normalize_sent(sent_posts)
    for post_id, sent_at in normalized:
        if post_id in state["seen_buffer_sent_ids"]:
            continue
        state["seen_buffer_sent_ids"][post_id] = sent_at
        state["verified_sent_count"] += 1
        count = state["verified_sent_count"]
        if count % BATCH_SIZE == BATCH_SIZE - 1:
            next_number = count // BATCH_SIZE + 1
            batch = state["pending_batch"]
            if batch is None or batch["number"] != next_number:
                draft, cursor = make_batch(
                    next_number, state["next_cursor"],
                    allocated_ids, allocated_titles)
                state["pending_batch"] = draft
                state["next_cursor"] = cursor
                allocated_ids.update(s["_reserve_id"] for s in draft["scripts"])
                allocated_titles.update(s["title"].casefold() for s in draft["scripts"])
                events.append("stage_next_ten")
        elif count % BATCH_SIZE == 0:
            next_number = count // BATCH_SIZE
            batch = state["pending_batch"]
            if batch is None or batch["number"] != next_number:
                batch, cursor = make_batch(
                    next_number, state["next_cursor"],
                    allocated_ids, allocated_titles)
                state["next_cursor"] = cursor
                events.append("late_stage_ten")
            state["active_batch"] = batch
            state["pending_batch"] = None
            events.append("promote_next_ten")
    state["last_polled_at"] = stamp
    validate_state(state)
    return state, events


def selected_scripts(state, catalog):
    """Only current active scripts, excluding already materialized episodes."""
    validate_state(state)
    active = state.get("active_batch")
    if not active:
        return []
    already = {e.get("story_reserve_id") for e in catalog.get("episodes", [])}
    return [deepcopy(s) for s in active["scripts"]
            if s["_reserve_id"] not in already]


def progress(state, scheduled_count=0):
    validate_state(state)
    return {
        "verified_buffer_sent_count_since_bootstrap": state["verified_sent_count"],
        "completed_ten_packs": state["verified_sent_count"] // BATCH_SIZE,
        "current_pack_progress": state["verified_sent_count"] % BATCH_SIZE,
        "active_pack": (state["active_batch"] or {}).get("number"),
        "active_script_drafts_ready": len((state["active_batch"] or {}).get("scripts", [])),
        "next_pack_prepared": state["pending_batch"] is not None,
        "next_script_drafts_ready": len((state["pending_batch"] or {}).get("scripts", [])),
        "buffer_scheduled_posts": scheduled_count,
        "note": "Prepared script drafts are not rendered/QA-passed MP4s.",
    }
