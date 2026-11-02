# GUSTAVA YouTube Factory: autonomous original LTX sources (2026-11-03)

Owner-controlled generation instead of exhausted third-party Pexels footage.

Verified hardware: Windows WIN-MFKU10DKMMC with RTX 4060 8GB; existing GUSTAVA-LTX-Video / ComfyUI localhost:8189 has the LTXV 2B distilled FP8 checkpoint and T5 encoder installed. A separate work folder was created at C:\\Users\\alex-\\GUSTAVA-YouTube-Factory-Bridge. Its original_scene_worker.py passed Python 3.11 compilation and --status tests. Windows Scheduled Task "GUSTAVA YouTube Factory Original Scenes" was registered for every 20 minutes. The first launch SKIPPED because ComfyUI had an existing task in progress, correctly protecting private GPU workloads.

Owner VPS hapych-eu-de-01, 85GB free at setup, uses SSH-only uploads and the read-only static origin https://84-252-66-87.sslip.io/yt-factory-originals/index.json. Initial manifest HTTP 200, provider gustava-ltx-original, sources []. Static nginx setup validated with nginx -t/reload. No public POST and no personal video browsing.

Generated source contract: exact host and HTTPS path, SHA256-file name matching original MP4, file size and duration recheck, one LTX 2B FP8 model, owner creator, LTX OpenRAIL-M provenance, two different independently generated scene actions in one batch, no mixed stock/AI author misattribution. Reject repeat footage in all permanent history. Actions from prompts are NOT proof of what video actually shows.

Autonomous GitHub intake: cloud-shorts/original_generated_source.py, moto_assets.py, source_story.py, editorial_guard.py, render_episode.py and moto_autocreate.py. It accepts real original clips, writes grounded two-action Russian episodes, checks actual video bytes, and retains exact Cartoon B reference, ASR, licensed-source checks and independent Qwen Vision actual-frame SHA review before any Buffer publishing. The autofill workflow alone has the fixed owner source feed URL. It does not set auto_publish manually. Tests test_original_generated_source.py cover rights, IDs, SHA, scenario actions and source cohort.

Current rollout is NOT a completed factory: actual original MP4 count remains 0 until user's ComfyUI becomes idle, both source MP4s render and pass motion tests, and arrive in VPS manifest. Earlier Buffer queue is 0. Subsequent valid live evidence must prove an independently approved original MP4, real Buffer queued post ID, sent state, public YouTube Shorts URL, and sustained 10 queued + 10 separate spare MP4. Never claim green source-intake CI alone as 10 finished posts.

Do not delete or modify user's existing videos/ComfyUI jobs. Do not republish the historical post list. Keep checkpoint in GitHub issue #80.
