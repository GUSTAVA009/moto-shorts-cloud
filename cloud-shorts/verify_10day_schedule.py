#!/usr/bin/env python3
"""Read-only reality check of exact ten-a-day posting slots in Buffer."""
from datetime import datetime, timezone
import json
from buffer_autopublish import verify_channel, CHANNEL
from ten_daily_slots import choose_slot, LOCAL_TIMES, TARGET_PER_DAY, MAX_POSTS_PER_DAY

def main():
    queue, recent = verify_channel(include_sent=True)
    next_due_at = choose_slot(queue + recent)
    print("GUSTAVA_BUFFER_SCHEDULING_CONFIGURED",
          json.dumps({"channel_id": CHANNEL,
                      "available_time_windows": TARGET_PER_DAY,
                      "max_actual_posts_per_day": MAX_POSTS_PER_DAY,
                      "local_timezone": "Europe/Moscow", "local_slots": [
                          "%02d:%02d" % pair for pair in LOCAL_TIMES],
                      "queued_posts": len(queue), "recent_sent": len(recent),
                      "content_queue_nonempty": bool(queue),
                      "next_safe_utc": next_due_at}, ensure_ascii=False))
    if not queue:
        print("::warning::BUFFER_SCHEDULE_SETUP_OK_BUT_ZERO_MP4_QUEUED: "
              "posting windows are NOT generated content", flush=True)
    print("READ_ONLY_AUDIT: no Buffer or YouTube posts created")

if __name__ == "__main__":
    main()
