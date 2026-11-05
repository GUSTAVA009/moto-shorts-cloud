# CLAUDE.md — GUSTAVA video formats

Before modifying or generating **any** Storyverse video, read these files:
- `../docs/STORYVERSE_2_FORMATS_VISUAL_QA_RU.md`
- `./format_profiles.json`

There are exactly **two accepted visual profiles**: `PAINTERLY_2D` and `HYBRID_2D3D`. Pick one explicitly for every episode. Preserve the approved visual appearance; don't silently change styles or substitute a different voice.

Use all relevant installed tools on the user's authorized PC, notably Claude Code, FFmpeg, Blender and Canvas/HTML when appropriate. Do **not** reconstruct a 3D action with independent inconsistent AI-generated images. Render characters and props as reusable rigs with fixed IDs, and program interactions by actual keyframe times.

For bus or vehicle sequences, verify doors physically clear the entrance and that characters do not clip, teleport, float or get cut off by the camera. Camera framing **must** be checked around action transitions, not just first/last frames. Sound recording silence is not action onset; trim blank sections and align the actual audible transient to the first movement frame.

Don't display logos, project title, episode index, scene number, workflow or diagnostic overlays inside the story video. Keep original characters, licensed audio, Russian narration GUSTAVA DEEP and accurate subtitles in a safe zone.

Mandatory gate before any attempt to publish:
1. Verify anatomy, objects, props and geometry in multiple frames across each action.
2. Verify script, visible actions, subtitles and all real SFX match.
3. Verify MP4 integrity, complete audio channels and frame pacing.
4. Obtain visual acceptance. **Do not auto-post unapproved draft or technical preview.**

State precisely what is verified and what remains unverified; never claim that a finished MP4 has no artifacts purely because FFmpeg decoding succeeds.
