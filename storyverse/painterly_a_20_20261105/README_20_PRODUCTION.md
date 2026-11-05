# GUSTAVA Storyverse — 20 vertical mystery Shorts (Painterly A)

This branch contains 20 **original Russian scripts** and 20 unique GUSTAVA DEEP narration recordings (each 120 seconds). Video generation runs locally on the user's authorized Windows desktop. Video reviews (not YouTube uploads) are delivered here:

https://github.com/GUSTAVA009/moto-shorts-cloud/releases/tag/gustava-painterly-A-20261105-20-review

## Real production stages

1. Source: `all_20_stories.json` (20 distinct stories, each six scenes).
2. Voices: `voices/*_GUSTAVA_DEEP_120s.mp3` (20 recordings; no Silero substitution).
3. Local graphics: `generate_sdxl_storyboards.py` via ComfyUI SDXL-Lightning, checkpoint `sdxl_lightning_4step.safetensors`.
4. Render: `assemble_painterly_sdxl.py` (1080×1920, 30 fps, 120 seconds; deterministic picture motion and snow overlay).
5. Run/resume batch: `produce_20_sdxl.py` (skips existing scenes and verifies output).
6. Preview uploads: `upload_review_previews.py` and `upload_review_watcher.py` (GitHub prerelease, no credentials in source).
7. Local detailed QA is saved in `episodes/<slug>/FINAL_VIDEO_QA.json`; preview downloads are **not** approved to publish on YouTube.

## Run from the existing Windows installation

The local working root is `C:\Users\alex-\GUSTAVA-AI-HUB\productions\PAINTERLY_A_NEXT_120_20261105`.

Start ComfyUI, ensure the model checkpoint exists and all narrated audio parts are complete, then use:

```powershell
py -3 .\produce_20_sdxl.py
py -3 .\upload_review_previews.py
```

The renderer is a **motion-illustration/slideshow approach**, explicitly allowed by the user for quick production, *not* full character animation. Physical actions, anatomy, scene continuity and subtitle/voice synchronization require separate editorial review before YouTube publishing.

**YouTube direct publishing is not connected.** Both AgentTube and the previous GitHub Actions pipeline lack valid Google OAuth. Never label a GitHub release as a YouTube publication. Validate the authorized channel ID before any live upload.

## Safeguards

- No project branding, series/scene/shot numbers or development overlays inside videos.
- Never replace the approved narrator voice.
- Do not use unrelated local videos or assets.
- All previews remain separate from live publishing.
- No automatic publication of videos whose `qa_visual` is pending or failed.
