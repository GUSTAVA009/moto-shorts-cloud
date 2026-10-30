# GUSTAVA Moto Shorts: 30-day breakout playbook
Prepared 2026-10-30. This is an editorial strategy and implementation specification, NOT confirmation that production automation has been modified or any new videos published.

## Objectives and current baseline
- Aspirational stretch goal: **one in ten QA-passed releases gets 1,000,000+ public views**. This is not a guaranteed or predictable distribution.
- Connected vidIQ check on 2026-10-30: GUSTAVA Enduro (@gustava009), 524 subscribers, 65,912 lifetime views, 67 public videos. These are not a retention baseline; per-video YouTube Studio data is needed.
- YouTube now distinguishes public views (from initial playback frame), engaged views, and stayed-to-watch (not swiped). Compare engaged views, retention, shares and new subscribers; not public starts alone. Source: https://support.google.com/youtube/answer/12220281
- YouTube explicitly says upload frequency and upload hour are not established drivers of long-term views. Quality beats an arbitrary ten-a-day target: https://support.google.com/youtube/answer/141805
- Reused/mass-produced, template-heavy uploads can jeopardize monetization: https://support.google.com/youtube/answer/1311392

## Promise to viewers
Short funny motorcycle situations, memorable riders/roads, surprising real details and useful lessons. One complete visual story per Short, with narration matching what actually happens. Russian script; approved GUSTAVA Create Audio Deep voice only. Do not use the previously excluded public words "Хапыч" or "эндуро" in published content.

## Editorial mix: precisely four comedy, three adrenaline, three useful out of ten
| Slot | Format | Starting hook | Required proof footage |
|---|---|---|---|
| 1 | Comedy | "Поехали на пятнадцать минут..." | Clearly filmed skit with true actor continuity or openly fictional POV |
| 2 | Comedy | "Механик: работы на пять минут" | Actual progressive disassembly, or an explicit fictional sketch |
| 3 | Comedy | "Друг обещал дорогу без грязи" | Muddy route reveal; do not pretend unrelated riders are the same person |
| 4 | Comedy | "Помыл байк — и пошёл дождь" | Real sequential gag, or labeled playful montage |
| 5 | Adrenaline | "Секунда до приземления" | Real jump and landing, no implied accident |
| 6 | Adrenaline | "Что скрывает этот поворот?" | Road action and meaningful revealed view |
| 7 | Transformation | "Этот байк не узнать!" | Verified same-bike before-and-after, otherwise change premise |
| 8 | Useful | "Почему опасен первый дождь?" | Matching wet-road scenes and defensible facts |
| 9 | Useful | "Что проверить на цепи?" | Real demonstrated chain inspection, no generic B-roll |
| 10 | Useful | "На что смотреть при примерке шлема?" | Visible fit/strap/visor actions; otherwise reject guide |

These are ideas, not approved ready MP4s. Comedy cannot present a fabricated accident or misleading real-world event as factual. Rights, voice, scene continuity and QA gate each episode.

## 12–25 second narrative structure (flexible, not mandatory padding)
- 0–1 second: the most arresting **actual** action or contrast, with a short readable title; no intro card.
- 1–5 seconds: concrete setup viewers understand even without riding expertise.
- 5–15 seconds: escalation, surprise, friction, visible progress or a relevant result.
- 15–23 seconds: honest visual payoff, useful reveal or punchline; optional natural replay loop.
- Final beat: one engaging question or precise promise about a future episode; no generic begging for subscriptions.

No seven-second stills, frozen footage, repeated scene loops, mismatched "tips", or meaningless montage. Preserve a single Deep narrator mixed without stereo doubled voice.

## Three-batch test: 30 independently created QA-passed Shorts
1. Produce three ten-slot batches at 4 comedy / 3 adrenaline / 3 useful each, changing location, characters, plot, motorcycle and hook between videos.
2. Within each genre experiment with an action hook, before/after contrast, or a one-sentence surprising question. Never upload near-duplicate variants for artificial A/B testing.
3. Record each episode's genre, hook type, length, Deep proof, visual QA, render receipt, Buffer queue ID, actual sent time, public URL and YouTube Analytics at 24h, 48h, and 7d.
4. Compare like-for-like age windows by **engaged views**, **stayed-to-watch**, **average percentage viewed**, **shares per 1,000 engaged views**, and **subscribers gained per 1,000 engaged views**. Segment by comedy, adrenaline and utility.
5. Early experimental signal: at least one of every ten exceeds the *preceding comparable median* engaged views by 10x, while passing originality and safety. Stretch goal: one in ten achieves 1M+ public views. These are project targets, not officially validated viral thresholds.
6. After 30 finished uploads, move up to 60% of slots toward clearly winning genres, keeping at least 20% novel format exploration and at least one useful video. Repeat format logic, never exact assets, wording or repeated scenes.
7. A video can take longer to reach a wide audience. Keep 7-day and 28-day performance checks rather than deleting slow starters.

## Production automation acceptance criteria
- Track separate pools: creative briefs; footage-cleared scripts; matching-pinned-Deep audio; genuinely renderable episodes; visually/audio QA-passed MP4s; Buffer scheduled; Buffer sent; YouTube confirmed.
- Count pending renderable originals only if matching audio is approved and available, the narration SHA256 matches, footage is rights-cleared and unused, and the story can visually prove the hook and payoff.
- When ready-stock is below a configurable floor, attempt safe replenishment and dispatch rendering. If no approved Deep file exists, report a specific Deep-supply blocker. Never substitute another voice or treat generic scripts as MP4 inventory.
- Buffer must never accept rejected/reused footage or a failed MP4. Duplicate reservation protection must be retained.
- **Ten per day is maximum planned capacity, not a command to flood YouTube.** Release fewer when genuine QA-passed content cannot be produced.
- Add automated tests for 4/3/3 content-class allocation, full story arc, pending-ready counts, Deep voice-only gate, visual evidence, rights, duplicate protection and the zero-unapproved-upload path.

## Existing gaps found in the repo
- moto_autocreate.py presently chooses mainly informative formats; its optional model is known to fall back to generic script templates.
- autofill_catalog.py treats auto_preview with no render receipt as pending inventory, even when the approved Deep audio is unavailable; prior GitHub runs showed BACKLOG_HEALTHY yet the renderer showed QUEUE_EMPTY.
- deep_voice.py consumes existing Deep recordings; it does not prove a supported unattended voice-generation API.
- On 2026-10-30, a GitHub Actions publisher received a Buffer queued post receipt for moto-riding-ritual-deep-20261030, so the upload-to-Buffer transport is real, but ten ready posts per day are not proven.

This is a **playbook and test specification**. It does not claim that all these automation features are live.
