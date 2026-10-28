# GUSTAVA — growth + human-like Russian narration

Public repo! Never commit private YouTube Studio analytics exports, tokens,
cookie files, reference voice recordings, or customer data.

## YPP rule

For full YouTube ad revenue: 1,000 real subscribers AND EITHER:
- 4,000 eligible public long-form watch hours over 365 days;
- 10 million eligible public Shorts views over 90 days.

Hours spent in the Shorts Feed do not count toward 4,000 hours. Public views
and eligible Shorts views differ. Eligibility alone does not guarantee approval.

Official sources:
https://support.google.com/youtube/answer/72851
https://support.google.com/youtube/answer/1311392

## Three content experiments

- Visual paradox: begin with genuine action and an observable puzzle within
  1.5 seconds; explain the underlying fact with verified sources.
- Rider story: a meaningful true anecdote with human commentary, varied
  licensed footage that supports the storyline, and a memorable ending.
- Mechanic challenge: actual before/after footage and a practical conclusion.
  Avoid unsupported safety advice and dangerous demonstrations.

Test 2–4 genuinely DIFFERENT original Shorts weekly. Publish one substantive
8–12 minute authored video weekly for qualifying long-form hours; no stretched
loops, borrowed clips without transformation, or endless identical templates.

## Data-driven pivot

Run growth analyzer with privately held Studio snapshot JSON, not GitHub logs:

    python cloud-shorts/growth_policy.py --snapshot local_private.json --output local_report.md

Optional: --previous previous_private.json. Source fields:
snapshot_date, subscribers, eligible_shorts_views_90d,
eligible_longform_watch_hours_365d, shorts_views_28d,
shorts_engaged_views_28d, shorts_subscribers_gained_28d,
viewed_instead_of_swiped_fraction (0–1),
average_short_viewed_fraction (optional),
shorts_with_48h_data, comparable_seven_day_views (optional).

When viewers choosing to watch <55% on enough impressions, A/B three
different hooks. When average viewed fraction <65%, tighten content pacing.
When subscriber conversions are weak, give a unique reason to subscribe.
Only classify a real decline after a comparable >=30% fall across 3 or more
mature Shorts (>=48 h old), not from the first 30 minutes or two-day Studio
processing delay. The output is an experiment proposal, never a promise.

## Claude Code integration

On the authorized Windows device, the direct first-party CLI can report no
login. Claude Code was successfully invoked using existing OmniRoute OAuth
gateway (read-only test):

    $env:HAPYCH_TEAM_MODEL='kiro/claude-sonnet-4.5'
    node "$HOME\.omniroute\maintenance\omni-with-auth.mjs" claude-print "<task>"

The local helper requires the PC to be online. Claude Code can orchestrate
FFmpeg, ASR, scripts, footage and TTS only by calling properly installed
external tools. For autonomous cloud operation, GitHub Actions/Buffer must be
separately configured and tested; local OAuth does not transfer to cloud CI.

Claude roles: evidence researcher, script editor, real-footage rights checker,
natural Russian voice director, ASR checker, FFmpeg editor, independent review,
publication gate, performance analyst. Never claim success until the MP4 and
platform publication are verified. Repeated formats need original substance.

## Natural voice is NOT an ASR score

Use voice_quality_gate.py to block words dropped by TTS, wrong endings,
clipping, abnormally long gaps and other objective defects. Human listening
approval of each NEW narrator/style is required before autopublishing;
automated ASR cannot certify that speech sounds human or has the right accent.
Do not falsely tell the audience an AI recording is a real voice actor.

Free local candidates for actual blind tests:
- Qwen3-TTS-12Hz-0.6B-Base, Apache-2.0, Russian:
  https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base
- Chatterbox Multilingual V3, MIT, Russian:
  https://github.com/resemble-ai/chatterbox

Do NOT assume superior quality before listening tests. RTX 4060 (8GB VRAM)
must not run several heavyweight TTS/video/GPU LLMs at once; schedule voice
benchmark separately or first free VRAM safely. Keep licensed original video,
distinct scripts, copyright provenance and a consistent narrator profile.

## Safety

No auto-posting when rights, voice or media QA is failing. No artificial
subscribers, fake view inflations, mass re-uploads or deceptive metadata.
The analyzer never alters posts or YouTube channel settings.
