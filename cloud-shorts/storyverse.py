#!/usr/bin/env python3
"""Original long-form Shorts fiction planning profile.

Planning is NOT rendering. This module must never claim uploaded/scheduled MP4,
switch approved voices, use reference footage, or auto-publish an episode.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERIES_FILE = PROJECT_ROOT / "series" / "original-chronicles" / "season1.json"
TARGET_COUNT = 19
SCENE_SECONDS = 6
DURATION = TARGET_COUNT * SCENE_SECONDS

class StoryverseError(ValueError):
    pass

def load_series(path: Path = SERIES_FILE) -> dict:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_series(obj)
    return obj

def validate_series(obj: dict) -> None:
    if not isinstance(obj, dict) or obj.get("schema_version") != 1:
        raise StoryverseError("Invalid storyverse schema")
    if obj.get("status") != "creative_package_not_video":
        raise StoryverseError("Cannot claim created MP4 from text drafts")
    if obj.get("reference_use") != "storytelling_format_analysis_only_no_source_media_no_character_copy_no_reproduced_audio":
        raise StoryverseError("Reference usage must be format-analysis-only")
    if obj.get("production_format", {}).get("resolution") != "1080x1920":
        raise StoryverseError("Require vertical 1080x1920")
    if obj["production_format"].get("fps") != 30 or obj["production_format"].get("duration_seconds") != DURATION:
        raise StoryverseError("Wrong Shorts export spec")
    if obj.get("voice_contract", {}).get("voice_id") != "deep":
        raise StoryverseError("Do not replace approved GUSTAVA DEEP")
    if obj["voice_contract"].get("fallback_forbidden") is not True:
        raise StoryverseError("No voice fallback permitted")
    if obj["publish_contract"].get("do_not_publish_creative_brief") is not True:
        raise StoryverseError("A script is not an MP4")
    if obj["publish_contract"].get("no_reference_frames_or_audio") is not True:
        raise StoryverseError("No reference media in output")
    if obj["publish_contract"].get("real_visual_audio_qa_required") is not True:
        raise StoryverseError("Visual/audio QA is mandatory")
    if obj["visual_style"].get("character_continuity_required") is not True:
        raise StoryverseError("Cannot render characters without continuity")
    for key in ("characters_do_not_speak", "mouth_animation_forbidden", "lip_sync_forbidden",
                "fixed_character_sprite_assets_required", "never_generate_character_faces_per_shot"):
        if obj["visual_style"].get(key) is not True:
            raise StoryverseError("Silent stable-character style required: " + key)
    if obj["voice_contract"].get("voice_is_offscreen_narrator_only") is not True:
        raise StoryverseError("Voice must be offscreen DEEP narration only")
    if obj["voice_contract"].get("character_dialogue_forbidden") is not True:
        raise StoryverseError("No speaking characters")
    for key in ("require_qa_no_facial_morphs", "require_qa_no_speaking_characters",
                "require_editorial_check_of_scene_action", "require_recheck_of_full_mixed_audio"):
        if obj["publish_contract"].get(key) is not True:
            raise StoryverseError("Required release gate missing: " + key)
    episodes = obj.get("episodes") or []
    if len(episodes) != 10:
        raise StoryverseError("Exactly ten original episode concepts required")
    ids, titles, premises = set(), set(), set()
    for ep in episodes:
        eid = ep.get("episode_id")
        title = ep.get("title", "").strip().casefold()
        premise = ep.get("original_premise", "").strip().casefold()
        if not isinstance(eid, str) or not re.fullmatch(r"\d{2}", eid):
            raise StoryverseError("Invalid episode ID")
        if eid in ids or title in titles or premise in premises:
            raise StoryverseError("Duplicated episode/plot")
        if len(title) < 8 or len(premise) < 35:
            raise StoryverseError("Incomplete story premise")
        ids.add(eid); titles.add(title); premises.add(premise)
    pilot = obj.get("pilot", {})
    if pilot.get("episode_id") not in ids or pilot.get("duration_seconds") != DURATION:
        raise StoryverseError("Pilot doesn't match series duration")
    if pilot.get("fictional") is not True:
        raise StoryverseError("Must not present fiction as factual news")
    scenes = pilot.get("shots") or []
    if len(scenes) != TARGET_COUNT:
        raise StoryverseError("Pilot must have exactly nineteen complete scenes")
    if not isinstance(pilot.get("characters"), dict) or len(pilot["characters"]) < 2:
        raise StoryverseError("Character bible missing")
    for i, shot in enumerate(scenes):
        if shot.get("scene") != i + 1:
            raise StoryverseError("Scene order broken")
        if (shot.get("start_sec"), shot.get("end_sec")) != (
            SCENE_SECONDS * i, SCENE_SECONDS * (i + 1)
        ):
            raise StoryverseError("Timing gap or overlap")
        for field, limit in (("narration_ru", 28), ("visual_action_ru", 25),
                             ("camera_ru", 10), ("sfx_ru", 3)):
            if len(str(shot.get(field, "")).strip()) < limit:
                raise StoryverseError(f"Scene {i + 1}: {field} missing")
    narration = " ".join(s["narration_ru"] for s in scenes)
    wc = len(narration.split())
    if not 185 <= wc <= 285:
        raise StoryverseError(f"114-second narration has implausible word count: {wc}")
    if "youtube.com" in narration.casefold() or "survive alert" in narration.casefold():
        raise StoryverseError("Source video copied into narration")

def episode_concept(series: dict, episode_id: str) -> dict:
    for episode in series["episodes"]:
        if episode["episode_id"] == episode_id:
            return episode
    raise StoryverseError(f"Unknown episode {episode_id}")

def next_unproduced_concept(series: dict, known_ids: set[str] | None = None) -> dict:
    used = known_ids or set()
    for episode in series["episodes"]:
        if episode["episode_id"] not in used and episode["status"] == "original_idea_only":
            return episode
    raise StoryverseError("No unused concepts; request new original ideas")

def plan_episode(series: dict, episode_id: str = "01") -> dict:
    concept = episode_concept(series, episode_id)
    if concept["status"] != "pilot_script_complete":
        raise StoryverseError("Outline only: generate and validate a complete 19-scene script first")
    return {
        "job_type": "creative_brief_not_rendered",
        "production_execution_status": "NOT_STARTED",
        "series_id": series["series_id"],
        "episode_id": episode_id,
        "title": concept["title"],
        "target_channel": series["target_channel_handle"],
        "story": series["pilot"],
        "visual_style": series["visual_style"],
        "production_format": series["production_format"],
        "voice_contract": series["voice_contract"],
        "publish_contract": series["publish_contract"],
        "reference_policy": series["reference_use"],
    }

def generate_draft(concept: dict, model: str, url: str = "http://127.0.0.1:11434/api/chat") -> dict:
    """Generate 19 script beats through local Ollama; never queues/renders/publishes.

    Validates the 19-scene constraint and leaves any failed output unissued.
    """
    instruction = (
        "You write ORIGINAL Russian-language serialized thriller/fiction Shorts."
        " No source-video copying, no existing franchise characters, no false 'true story' claims."
        " Genre: " + concept["genre"] + ". Original premise: " + concept["original_premise"] +
        ". Create a coherent exactly 19-scene story with ONE continuing hero, goal,"
        " escalating stakes, earned rescue/resolution, and a fresh final hook AFTER the payoff."
        " The main narration must be 195-265 words in natural Russian."
        " Each scene must be a short Russian spoken phrase, 10-16 words, matching"
        " one clearly visible cause-and-effect action. Uncluttered shot continuity."
        " Visual style: entirely ORIGINAL simple illustrated outlined 2D character faces"
        " and thin bodies over cinematic 3D low-poly locations. Never use any reference footage."
        " Answer JSON object only with fields 'characters' (object of 2-4 named stable"
        " visual identities with detailed costumes) and 'shots' (array of EXACTLY nineteen"
        " objects with keys narration_ru, visual_action_ru, camera_ru, sfx_ru)."
        " Russian captions must be sourced from narration, not invented on visuals."
    )
    payload = {
        "model": model, "stream": False, "think": False, "format": "json",
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": "Write one new original episode titled " + concept["title"]}],
        "options": {"num_ctx": 8192, "num_predict": 4400, "temperature": 0.65},
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=raw, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=260) as response:
        data = json.load(response)
    body = (data.get("message") or {}).get("content") or ""
    candidate = json.loads(body)
    if not isinstance(candidate, dict) or not isinstance(candidate.get("shots"), list):
        raise StoryverseError("Model output is not a scene screenplay")
    if len(candidate["shots"]) != TARGET_COUNT:
        raise StoryverseError("Model must return exactly 19 shots, not a truncated script")
    normalized = []
    for i, shot in enumerate(candidate["shots"]):
        normalized.append({
            "scene": i + 1, "start_sec": i * SCENE_SECONDS,
            "end_sec": (i + 1) * SCENE_SECONDS,
            **{k: str(shot.get(k, "")).strip() for k in
               ("narration_ru", "visual_action_ru", "camera_ru", "sfx_ru")},
        })
    pilot = {
        "episode_id": concept["episode_id"], "title": concept["title"], "fictional": True,
        "duration_seconds": DURATION, "characters": candidate.get("characters", {}),
        "shots": normalized,
    }
    # Apply the same shot and timing checks used for the owner-reviewed pilot.
    trial = {**load_series(), "pilot": pilot}
    validate_series(trial)
    return pilot

def main() -> None:
    p = argparse.ArgumentParser()
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate", action="store_true")
    mode.add_argument("--list", action="store_true")
    mode.add_argument("--pilot-brief", action="store_true")
    mode.add_argument("--next", action="store_true")
    args = p.parse_args()
    series = load_series()
    if args.validate:
        print("VALID", series["series_id"], "19 scenes", "10 original concepts", "NOT_RENDERED")
    elif args.list:
        print(json.dumps(series["episodes"], ensure_ascii=False, indent=2))
    elif args.next:
        print(json.dumps(next_unproduced_concept(series), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(plan_episode(series), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
