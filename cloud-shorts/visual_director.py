"""GUSTAVA visual direction: illustrated topic, chronological scene sequence.

This is an editorial *fail-closed* gate, not a claim that stock metadata can
replace a human actually watching the footage. It deliberately ignores
user-supplied broad "topics" tags, which previously marked handlebar closeups
as helmet footage. Scenes show each source once rather than ping-pong edits.
"""
from __future__ import annotations

import hashlib
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

# A noun in the title is NOT evidence of the described action. An instructional
# helmet Short needs actual sources of FITTING, FASTENING and VISOR operation.
# These keywords must occur in the provider page slug, not a fabricated tag
# or model-authored "source_title". They are only a preflight; the final action
# still needs review of actual video frames before the release is approved.
HELMET_CLAIMS = (
    ("helmet_fit", re.compile(r"размер|посадк|плотно|болта|давит|сидит", re.I),
     re.compile(r"adjust|fitt?ing|try(?:ing)?-on|putting-on|"
                r"подгон|пример", re.I)),
    ("helmet_strap", re.compile(r"ремеш|застег|подбород", re.I),
     re.compile(r"strap|buckle|fasten|chin-strap|ремеш|застег", re.I)),
    ("helmet_view", re.compile(r"обзор|визор|поле.{0,6}зрени", re.I),
     re.compile(r"visor|view-through|opening-the-visor|closing-the-visor|"
                r"визор|обзор", re.I)),
)
PASSIVE_PORTRAIT = re.compile(
    r"(close-up|portrait|posing|wearing|looking|helmet-on-a-handlebar)", re.I
)
VISIBLE_ACTION = re.compile(
    r"(adjust|fitt?ing|fasten|strap|buckle|putting-on|taking-off|"
    r"riding|race|repair|ride|travel(?:ing|ling)?|remov|closing|opening|checking|working|install)", re.I
)



SCENE_ACTION_SLUGS = {
    "visor_close": re.compile(r"closing-(?:the-)?visor|visor-closing|"
                              r"lowering-(?:the-)?visor", re.I),
    "riding": re.compile(r"travel(?:ing|ling)?-on-a-motorbike|riding|"
                         r"ride|motorcycle-on-road|racing", re.I),
    "helmet_removal": re.compile(r"removing-(?:his-|her-|their-)?helmet|"
                                 r"taking-off-(?:the-)?helmet", re.I),
}


def verify_scene_script_anchors(episode):
    """Optional exact proof of scripted chapter order and action metadata."""
    beats=episode.get("scene_script_anchors")
    if beats is None:
        return None
    if not isinstance(beats,list) or not (2<=len(beats)<=5):
        raise ValueError("VISUAL_BEATS_INVALID: expected 2-5 distinct chapters")
    narration=str(episode.get("narration") or "").casefold()
    sources={s["key"]:s for s in episode.get("footage") or []}
    used=set()
    prior=-1
    for b in beats:
        key=b.get("source")
        action=b.get("action")
        anchor=str(b.get("spoken_anchor") or "").casefold()
        matcher=SCENE_ACTION_SLUGS.get(action)
        at=narration.find(anchor)
        if (key not in sources or key in used or not matcher or len(anchor)<8
                or at<=prior or not matcher.search(provider_slug(sources[key]))):
            raise ValueError(
                "VISUAL_BEATS_OFF_SCRIPT: shot must show the actual narrated "
                "action at its first distinct scripted occurrence"
            )
        prior=at
        used.add(key)
    return [b["source"] for b in beats]

def instructional_claims(episode):
    """Action codes and their original order in the actual Russian narration."""
    if main_subject(episode) != "helmet":
        return []
    narration = str(episode.get("narration") or "")
    found = [(m.start(), code) for code,pattern,_ in HELMET_CLAIMS
             if (m := pattern.search(narration))]
    return [code for _,code in sorted(found)]


def provider_slug(source):
    """Treat only the independent provider URL as a preflight caption."""
    return urlparse(str(source.get("source_page") or "")).path.lower()


def visual_asset_fingerprint(episode):
    """Bind a human review to precise script, scene URLs, and action plan."""
    data={
        "narration":episode.get("narration"),
        "footage":[{field:s.get(field) for field in ("key","source_page","url")}
                   for s in episode.get("footage") or []],
        "shots":episode.get("shots") or [],
        "visual_beats":episode.get("visual_beats") or [],
    }
    return hashlib.sha256(json.dumps(
        data,ensure_ascii=False,sort_keys=True,separators=(",",":")
    ).encode("utf8")).hexdigest()


def verify_action_storyboard(episode):
    """No tutorial release based solely on a nice helmet close-up."""
    actions=instructional_claims(episode)
    if len(actions)<2:
        return []
    source_map={s["key"]:s for s in episode.get("footage") or []}
    # Newly generated v3 instructions require an explicit shot per spoken step.
    beats=episode.get("visual_beats")
    if not isinstance(beats,list) or [b.get("action") for b in beats]!=actions:
        raise ValueError(
            "VISUAL_ACTION_STORYBOARD_MISSING: tutorial needs precisely "
            "ordered filmed steps "+", ".join(actions)
        )
    used=set()
    for beat in beats:
        key=beat.get("source")
        action=beat["action"]
        source=source_map.get(key)
        matcher=next(pat for code,_,pat in HELMET_CLAIMS if code==action)
        if (not source or key in used or not matcher.search(provider_slug(source))):
            raise ValueError("VISUAL_ACTION_MISMATCH: "+action+
                             " lacks distinct provider footage of that action")
        used.add(key)
    # Metadata alone cannot verify an unbuckled strap or safe fit. An actual
    # visual review is explicitly required before auto-publication.
    if episode.get("auto_publish") is True:
        evidence=episode.get("visual_review") or {}
        if (evidence.get("status")!="human_approved"
                or evidence.get("asset_fingerprint")!=visual_asset_fingerprint(episode)):
            raise ValueError(
                "VISUAL_REVIEW_REQUIRED: metadata cannot prove helmet fastening "
                "or fit; a video-frame reviewer must approve exact assets."
            )
    return actions


def scene_duration_limit(episode, source):
    """New stories cannot hold a passive portrait for seven seconds."""
    if int(episode.get("visual_director_version") or 0)<3:
        return MAX_SCENE_SECONDS
    slug=provider_slug(source)
    if PASSIVE_PORTRAIT.search(slug) and not VISIBLE_ACTION.search(slug):
        return 3.5
    if VISIBLE_ACTION.search(slug) and not re.search(r"riding|race|ride|travel",slug):
        return 6.0
    if re.search(r"riding|race|ride|travel", slug):
        # Exception for a *documented real moving ride*, never a passive
        # portrait or stationary helmet. Two original long scenes should
        # cover the narrator without padding, repetition or speed-up.
        cap = float(episode.get("active_ride_scene_seconds", 8.0))
        if not 8.0 <= cap <= 10.0:
            raise ValueError("Unsafe requested moving scene length")
        return cap
    return 8.0




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
    if (episode.get("auto_publish") is True
            or int(episode.get("visual_director_version") or 0)>=3):
        verify_action_storyboard(episode)
        verify_scene_script_anchors(episode)
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
    # Tutorials follow the story's actual spoken actions, not shuffled source IDs.
    # For travel/cinematic footage the established authored shot order remains.
    evidence_set=set(evidence["evidence_sources"])
    order=list(first)
    claims=instructional_claims(episode)
    if int(episode.get("visual_director_version") or 0)>=3 and len(claims)>=2:
        order=[beat["source"] for beat in episode["visual_beats"]]
    elif int(episode.get("visual_director_version") or 0)>=3 and episode.get("scene_script_anchors"):
        order=verify_scene_script_anchors(episode)
    elif evidence_set:
        order.sort(key=lambda key: (key not in evidence_set, list(first).index(key)))
    # Prefer up to 3 scenes, rather than endless sub-two-second cuts.
    n=min((5 if int(episode.get("visual_director_version") or 0)>=3 else 3),
          len(order),int(target//MIN_SCENE_SECONDS))
    if n<2:
        raise RuntimeError("VISUAL_SCENE_SHORTAGE: cannot plan 2 readable scenes")
    order=order[:n]
    src_by_key={s["key"]:s for s in episode["footage"]}
    caps=[]
    for key in order:
        duration=float(source_durations[key])
        available=max(0.,duration-first[key]-.18)
        caps.append(min(scene_duration_limit(episode,src_by_key[key]),available))
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
        raise RuntimeError(
            "VISUAL_SCENE_SHORTAGE: need more action-specific footage; "
            "never pad with repeated or seven-second static helmets"
        )
    plan=[{"source":key,"start":round(first[key],3),"seconds":round(length,3)}
          for key,length in zip(order,portions)]
    if len({x["source"] for x in plan})!=len(plan):
        raise AssertionError("Directing produced a repeated source")
    if evidence_set and plan[0]["source"] not in evidence_set:
        raise AssertionError("Topic subject not visible at the opening")
    if int(episode.get("visual_director_version") or 0)>=3 and len(claims)>=2:
        if [p["source"] for p in plan]!=[b["source"] for b in episode["visual_beats"]]:
            raise RuntimeError("VISUAL_ACTION_ORDER_MISMATCH: every spoken step needs its shot")
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
    expected_version=(3 if int(episode.get("visual_director_version") or 0)>=3 else 2)
    max_scenes=(5 if expected_version==3 else 3)
    if (obj.get("version")!=expected_version or obj.get("passed") is not True
            or obj.get("episode")!=episode["id"]
            or not 2<=len(seq)<=max_scenes
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
