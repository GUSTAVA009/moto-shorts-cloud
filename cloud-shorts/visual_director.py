"""GUSTAVA visual direction: illustrated topic, chronological scene sequence.

This is an editorial *fail-closed* gate, not a claim that stock metadata can
replace a human actually watching the footage. It deliberately ignores
user-supplied broad "topics" tags, which previously marked handlebar closeups
as helmet footage. Scenes show each source once rather than ping-pong edits.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from urllib.parse import urlparse

# Deliberately strict when the actual TITLE makes the object the subject.
# Metadata is a *preflight* signal: a visual reviewer can still reject it.
OBJECTS = {
    "helmet": (
        re.compile(r"\bшлем\w*|\bмотошлем\w*|\bhelmet\w*|\bhelm\b", re.I),
        re.compile(r"motorcycle.?(?:helmet|helm)|motorbike.?(?:helmet|helm)|"
                   r"helmet|helmets|шлем|head.protection", re.I),
    ),
    "chain": (
        re.compile(r"\bцеп\w*|\bchain\b", re.I),
        re.compile(r"\bchain\b|цепь|sprocket", re.I),
    ),
    "tires": (
        re.compile(r"\bшин\w*|\bпокрыш\w*|\btyre\w*|\btire\w*", re.I),
        re.compile(r"tire|tyre|wheel|шин|покрыш", re.I),
    ),
    "brakes": (
        re.compile(r"\bтормоз\w*|\bbrake\w*", re.I),
        re.compile(r"brake|тормоз|disc|caliper", re.I),
    ),
}

MIN_SCENE_SECONDS = 3.3
MAX_SCENE_SECONDS = 12.0


def main_subject(episode):
    title = str(episode.get("title", ""))
    for key, (mentioned, _) in OBJECTS.items():
        if mentioned.search(title):
            return key
    return None


def source_evidence(source):
    """Provider-supplied source title & URL, NEVER the self-assigned topic list."""
    title = str(source.get("source_title") or "")
    path = urlparse(str(source.get("source_page") or "")).path
    return (title + " " + path).casefold()


def subject_sources(episode):
    subject = main_subject(episode)
    if subject is None:
        return [], None
    matches = [src["key"] for src in episode.get("footage", ())
               if OBJECTS[subject][1].search(source_evidence(src))]
    return matches, subject


def verify_story_subject(episode):
    matches, subject = subject_sources(episode)
    if subject is not None and not matches:
        raise ValueError(
            "VISUAL_TOPIC_MISMATCH: narration/title focuses on "+subject+
            " but none of the provider source titles actually confirms it. "
            "Do not upload unrelated motorcycle footage."
        )
    shots = episode.get("shots") or []
    sources = {src.get("key") for src in episode.get("footage", ())}
    if len(sources) < 2 or any(shot.get("source") not in sources for shot in shots):
        raise ValueError("VISUAL_STORY_UNVERIFIED: missing actual video source")
    return {"subject": subject, "evidence_sources": matches,
            "source_count": len(sources)}


def directed_plan(episode, source_durations, seconds):
    """Unique, comprehensible ~4-10s source blocks; never A/B/A/B flashing."""
    evidence = verify_story_subject(episode)
    target = float(seconds)
    if not 7 <= target <= 36:
        raise ValueError("Invalid total visual length")
    first = {}
    for shot in episode.get("shots") or []:
        key=shot["source"]
        if key not in first:
            first[key]=float(shot.get("start", 0.))
    if len(first)<2:
        raise RuntimeError("VISUAL_SCENE_SHORTAGE: need 2 independent moving scenes")
    # Evidence first: if you say "helmet", the helmet must appear immediately.
    evidence_set=set(evidence["evidence_sources"])
    order=list(first)
    if evidence_set:
        order.sort(key=lambda key: (key not in evidence_set, list(first).index(key)))
    # Prefer up to 3 scenes, rather than endless sub-two-second cuts.
    n=min(3,len(order),int(target//MIN_SCENE_SECONDS))
    if n<2:
        raise RuntimeError("VISUAL_SCENE_SHORTAGE: cannot plan 2 readable scenes")
    order=order[:n]
    caps=[]
    for key in order:
        duration=float(source_durations[key])
        available=max(0.,duration-first[key]-.18)
        caps.append(min(MAX_SCENE_SECONDS,available))
    if sum(caps)<target-.12 or any(cap<MIN_SCENE_SECONDS for cap in caps):
        raise RuntimeError("VISUAL_DURATION_SHORTAGE: need more suitable licensed source footage")
    portions=[min(target/n,cap) for cap in caps]
    remaining=target-sum(portions)
    for i,cap in enumerate(caps):
        add=min(max(0.,cap-portions[i]),remaining)
        portions[i]+=add
        remaining-=add
        if remaining<=.025:
            break
    if remaining>.12 or any(x<MIN_SCENE_SECONDS for x in portions):
        raise RuntimeError("VISUAL_SCENE_SHORTAGE: one readable block would be too short")
    plan=[{"source":key,"start":round(first[key],3),"seconds":round(length,3)}
          for key,length in zip(order,portions)]
    if len({x["source"] for x in plan})!=len(plan):
        raise AssertionError("Directing produced a repeated source")
    if evidence_set and plan[0]["source"] not in evidence_set:
        raise AssertionError("Topic subject not visible at the opening")
    return plan


def verified_visual_artifact(episode, mp4_path):
    """Read renderer's QA proof before publishing any new director-v2 episode.

    For historical unmodified releases keep legacy compatibility but still
    reject an object guide whose footage is unrelated to its main subject.
    """
    evidence=verify_story_subject(episode)
    path=Path(mp4_path).parent/"visual_qa.json"
    required=episode.get("visual_director_version",0) >= 2
    if not path.is_file():
        if required:
            raise ValueError("VISUAL_QA_MISSING: new publication requires genuine visual plan proof")
        return {"legacy":True,"passed":False}
    try:
        obj=json.loads(path.read_text(encoding="utf8"))
    except (OSError,ValueError,TypeError) as exc:
        raise ValueError("VISUAL_QA_CORRUPT") from exc
    seq=obj.get("source_sequence") or []
    plan=obj.get("sequence") or []
    known={x["key"] for x in episode["footage"]}
    if (obj.get("version")!=2 or obj.get("passed") is not True
            or obj.get("episode")!=episode["id"]
            or not 2<=len(seq)<=3
            or len(set(seq))!=len(seq)
            or set(seq)-known or len(plan)!=len(seq)
            or [p.get("source") for p in plan]!=seq
            or any(float(p.get("seconds",0))<MIN_SCENE_SECONDS for p in plan)
            or obj.get("source_reused_in_short") is not False):
        raise ValueError("VISUAL_QA_REJECTED: repeated/missing/corrupt visual chapters")
    if evidence["subject"] is not None:
        if obj.get("subject")!=evidence["subject"] or seq[0] not in evidence["evidence_sources"]:
            raise ValueError("VISUAL_TOPIC_MISMATCH: story object not shown first")
    return obj
