"""Only original self-hosted Qwen and historical DEEP may start private QA.

An API candidate and script are not a finished MP4. Maintain truthful stages.
"""
from __future__ import annotations
import os
from voice_failover import available_routes

from deep_voice import ready as deep_ready, VOICE_ENGINE as DEEP_ENGINE
from selfhosted_voice import ready as local_ready, VOICE_ENGINE as LOCAL_ENGINE


def inventory(catalog, reserved_ids, environment=None):
    env = os.environ if environment is None else environment
    reserved=set(reserved_ids)
    waiting=[
        ep for ep in catalog.get("episodes",[])
        if ep.get("auto_preview") is True and ep.get("id") not in reserved
        and ep.get("editorial_rejected") is not True
        and ep.get("visual_review_failed") is not True
    ]
    old=[ep for ep in waiting if ep.get("voice_engine")==DEEP_ENGINE]
    old_ready=[ep for ep in old if deep_ready(ep)]
    new=[ep for ep in waiting if ep.get("voice_engine")==LOCAL_ENGINE]
    new_ready=[ep for ep in new if local_ready(ep,env)]
    routes=available_routes(env,require_secret=False)
    rejected=[ep for ep in catalog.get("episodes",[])
              if ep.get("editorial_rejected") is True
              or ep.get("visual_review_failed") is True]
    blockers=[]
    if len(old_ready)<len(old):
        blockers.append("UNATTENDED_DEEP_TTS_PROVIDER_NOT_CONNECTED")
    if len(new_ready)<len(new):
        blockers.append("NO_CONFIGURED_OWNER_CLOUD_WINDOWS_OR_THIRD_VOICE")
    return {
        "unrendered_script_drafts":len(waiting),
        "unrendered_verified_deep_originals":len(old_ready),
        "unrendered_missing_original_deep":len(old)-len(old_ready),
        "unrendered_selfhosted_api_candidates":len(new_ready),
        "unrendered_selfhosted_not_configured":len(new)-len(new_ready),
        "rejected_visuals":len(rejected),
        "has_autonomous_deep_tts":False,
        "has_selfhosted_api_configured":bool(routes),
        "configured_voice_route_names":[route.name for route in routes],
        "voice_route_reachability_verified":False,
        "ready_unattended_voice_episodes":len(old_ready)+len(new_ready),
        "blockers":blockers,
    }


def production_unavailable(state):
    return (state["unrendered_verified_deep_originals"] == 0 and
            state.get("unrendered_selfhosted_api_candidates",0)==0)
