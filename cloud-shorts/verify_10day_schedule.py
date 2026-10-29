#!/usr/bin/env python3
"""Read-only reality check of exact ten-a-day posting slots in Buffer."""
from datetime import datetime, timezone
import json
from buffer_autopublish import verify_channel, CHANNEL
from ten_daily_slots import choose_slot, LOCAL_TIMES, TARGET_PER_DAY

def main():
    queue, recent = verify_channel(include_sent=True)
    next_due_at = choose_slot(queue + recent)
    print("GUSTAVA_BUFFER_10_PER_DAY_READY",
          json.dumps({"channel_id": CHANNEL, "target_slots": TARGET_PER_DAY,
                      "local_timezone": "Europe/Moscow", "local_slots": [
                          "%02d:%02d" % pair for pair in LOCAL_TIMES],
                      "queued_posts": len(queue), "recent_sent": len(recent),
                      "next_safe_utc": next_due_at}, ensure_ascii=False))
    print("READ_ONLY_AUDIT: no Buffer or YouTube posts created")

if __name__ == "__main__":
    main()
