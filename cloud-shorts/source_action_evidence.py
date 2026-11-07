"""Fail-closed source ACTION preflight from SHA-pinned actual native video frames.

The previous production system trusted stock-video *titles*. This permitted
a helmet-donning narration over parked riders, a street-traffic narration
over an empty street, and 'riding' over people pushing motorcycles.
The source evidence below only qualifies a dynamic clip for story drafting;
it is NEVER an automatic approval to publish. Full final MP4 six-frame
and narration agreement review remains mandatory at release time.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

HERE=Path(__file__).resolve().parent
EVIDENCE=HERE/"native_source_action_evidence.json"
_SHA=re.compile(r"[0-9a-f]{64}\Z")
_ALLOWED_DYNAMIC=("riding","stunt_jump")
_MODEL="qwen3.5:4b"


def _source_id(source):
    parsed=urlsplit(str(source.get("url") or ""))
    match=re.fullmatch(r"/download/video/([0-9]{4,12})/?",parsed.path)
    if (parsed.scheme!="https" or parsed.hostname!="www.pexels.com"
            or parsed.username or parsed.password or parsed.query
            or parsed.fragment or not match):
        return None
    return match.group(1)


def load_evidence(path=None):
    source=EVIDENCE if path is None else Path(path)
    if not source.is_file():
        return {}
    doc=json.loads(source.read_text(encoding="utf8"))
    if (doc.get("version")!=1 or not isinstance(doc.get("reports"),list)
            or len(doc["reports"])>5000):
        raise RuntimeError("SOURCE_VISUAL_EVIDENCE_MANIFEST_INVALID")
    reports={}
    for item in doc["reports"]:
        if not isinstance(item,dict):
            raise RuntimeError("SOURCE_VISUAL_EVIDENCE_ROW_INVALID")
        sid=item.get("source_id")
        if (not isinstance(sid,str) or not sid.isdigit()
                or sid in reports):
            raise RuntimeError("SOURCE_VISUAL_EVIDENCE_DUPLICATE_OR_BAD_ID")
        reports[sid]=item
    return reports


def source_dynamic_action_verified(source, reports=None):
    """Keep static/pushed/unknown footage OUT of unattended story selection."""
    if not isinstance(source,dict):
        return False
    sid=_source_id(source)
    if not sid:
        return False
    if reports is None:
        reports=load_evidence()
    row=reports.get(sid)
    if not isinstance(row,dict):
        return False
    families=[p for p in ("2k","4k") if source.get("native_"+p+"_sha256")]
    if len(families)!=1:
        return False
    family=families[0]
    expected_sha=source.get("native_"+family+"_sha256")
    if not isinstance(expected_sha,str) or not _SHA.fullmatch(expected_sha):
        return False
    if row.get("sha256")!=expected_sha:
        return False
    if (row.get("width") != source.get("native_"+family+"_width")
            or row.get("height") != source.get("native_"+family+"_height")):
        return False
    frames=row.get("frame_sha256")
    if (not isinstance(frames,list) or len(frames)!=3
            or not all(isinstance(x,str) and _SHA.fullmatch(x) for x in frames)):
        return False
    confidence=row.get("confidence")
    return bool(
        row.get("model")==_MODEL
        and row.get("action") in _ALLOWED_DYNAMIC
        and row.get("motorcycle_visible") is True
        and row.get("action_visually_confirmed") is True
        and row.get("candidate_dynamic_action") is True
        and type(confidence) in (float,int) and confidence>=.92
        and isinstance(row.get("observed"),str)
        and 15<=len(row["observed"])<=240)


def verified_riding_context(source, reports=None):
    """A real-frame evidence-derived setting, never a guessed page tag.

    Two riding clips can tell a useful original how-it-changes-by-surface
    story. This is NOT a claim that their riders or events are related.
    Only accept a setting when the same SHA-pinned, independently reviewed
    original is verified to show actual riding.
    """
    if reports is None:
        reports=load_evidence()
    if not source_dynamic_action_verified(source,reports):
        return None
    row=reports.get(_source_id(source),{})
    if row.get("action")!="riding":
        return None
    seen=str(row.get("observed") or "").casefold()
    patterns=(
       ("sand",r"песчан\w*|по песку"),
       ("trail",r"лесн\w* троп|грунтов\w* дорог"),
       ("garage",r"парковк\w* под земл|подземн\w* парк"),
       ("alley",r"узк\w* улиц|промышленн\w* район"),
       ("city",r"городск\w* улиц"),
       ("road",r"асфальтированн\w* дорог|сельск\w* местн"),
    )
    found=[key for key,pattern in patterns if re.search(pattern,seen)]
    return found[0] if len(found)==1 else None


def require_episode_dynamic_sources(episode, reports=None):
    """This blocks queued ungrounded scenes *before* reserving an episode."""
    footage=episode.get("footage") or []
    if len(footage)!=2:
        raise ValueError("SOURCE_VISUAL_TWO_ACTION_SCENES_REQUIRED")
    if reports is None:
        reports=load_evidence()
    failures=[x.get("key") for x in footage
              if not source_dynamic_action_verified(x,reports)]
    if failures:
        raise ValueError("SOURCE_VISUAL_ACTUAL_RIDING_NOT_PROVEN:"+
                         ",".join(str(x) for x in failures))
    # The first failed 2K batch contained two genuinely moving motorbikes,
    # yet its voice invented "more cars" in an otherwise empty street.
    # Do not infer other traffic from a verified riding action.
    script=str(episode.get("narration") or "").casefold()
    unproven_traffic=(
        r"(?:много|больше|плотн\w*|оживл[её]нн\w*)\s+"
        r"(?:машин|автомобил\w*|трафик\w*|транспорт\w*)"
        r"|(?:машин|автомобил\w*|трафик\w*|транспорт\w*)\s+"
        r"(?:много|больше|плотн\w*)"
        r"|\bпробк\w*\b")
    if re.search(unproven_traffic,script):
        raise ValueError("SOURCE_VISUAL_UNVERIFIED_TRAFFIC_CLAIM")
    actions=[reports[_source_id(x)]["action"] for x in footage]
    if re.search(r"прыж\w*|трамплин\w*",script) and "stunt_jump" not in actions:
        raise ValueError("SOURCE_VISUAL_UNVERIFIED_JUMP_CLAIM")
    if re.search(r"надев\w*\s+шлем|надева\w*\s+шлем",script) and "helmet_put_on" not in actions:
        raise ValueError("SOURCE_VISUAL_UNVERIFIED_HELMET_CLAIM")
    if re.search(r"ремонт\w*|чинит|почин\w*",script) and "maintenance" not in actions:
        raise ValueError("SOURCE_VISUAL_UNVERIFIED_REPAIR_CLAIM")
    return True
