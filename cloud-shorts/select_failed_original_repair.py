#!/usr/bin/env python3
"""Find one genuine failed private owner-original MP4 eligible for phonetic repair.

Not a publisher. Never edits episodes, bypasses ASR, reuses visuals, or uploads.
Scans immutable SHA/QA render ledger and the actual GitHub workflow run before
downloading exactly one failure artifact for existing bounded rewrite logic.
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import re
import hashlib

from preview_queue import preview_fingerprint
from autofill_catalog import github
from moto_assets import source_id
from selfhosted_voice import CARTOON_B_REFERENCE_SHA, CARTOON_B_PROFILE_ID


def decode_entry(entry):
    if not entry or not isinstance(entry.get("content"),str):
        raise RuntimeError("PHONETIC_REPAIR_INVALID_LEDGER_BLOB")
    return json.loads(base64.b64decode(entry["content"]))


def eligible_episode(ep, receipt):
    try:
        count = receipt.get("attempt_count") if isinstance(receipt,dict) else None
        proof = ep.get("voice_revision_evidence") or {}
        if type(count) is not int or count<1:
            return False
        if count > 1:
            # A previously revised script is eligible for one further
            # DIFFERENT correction only after its new real MP4 failed ASR.
            if (ep.get("voice_revision_requested") is not True
                    or not isinstance(proof,dict)
                    or proof.get("prior_run_id") != str(receipt.get("previous_run_id"))
                    or proof.get("new_narration_sha256") != hashlib.sha256(
                        str(ep.get("narration") or "").encode("utf8")).hexdigest()):
                return False
        elif ep.get("voice_revision_requested"):
            return False
        if receipt.get("preview_fingerprint") != preview_fingerprint(ep):
            return False  # Do not re-repair an older run after catalog changed.
    except (ValueError, TypeError, KeyError, RuntimeError):
        return False
    return bool(
        ep.get("auto_preview") is True
        and ep.get("auto_publish") is False
        and ep.get("voice_engine") == "gustava_selfhosted_qwen3"
        and ep.get("voice_profile") == CARTOON_B_PROFILE_ID
        and ep.get("selfhosted_voice_id") == "gustava-cartoon-b-v1"
        and len(ep.get("footage") or []) == 2
        and all(source_id(s).startswith("gustava-original-")
                for s in ep["footage"])
        and isinstance(receipt,dict)
        and receipt.get("id") == ep["id"]
        and receipt.get("state") == "preview_ready"
        and receipt.get("voice_qa_passed") is False
        and receipt.get("mixed_audio_qa_passed") is False
        and receipt.get("selfhosted_reference_sha256") == CARTOON_B_REFERENCE_SHA
        and type(receipt.get("attempt_count")) is int
        and receipt.get("attempt_count") >= 1
        and re.fullmatch(r"[a-f0-9]{64}",str(receipt.get("preview_fingerprint") or ""))
        and str(receipt.get("run_id") or "").isdigit()
    )


def select_one(episodes,paths,api=github,requested_run_id=""):
    pathset=set(paths)
    for ep in reversed(episodes):
        slug=ep.get("id","")
        if ("render-receipts/"+slug+".json" not in pathset
                or "buffer-publication-receipts/"+slug+".json" in pathset
                or "publication-receipts/"+slug+".json" in pathset
                or not (ep.get("auto_publish") is False and
                        ep.get("voice_engine") == "gustava_selfhosted_qwen3" and
                        len(ep.get("footage") or []) == 2 and
                        all(f.get("license")=="LTX OpenRAIL-M"
                            for f in ep["footage"]))):
            continue
        receipt=decode_entry(api("GET","contents/render-receipts/"+
                                 slug+".json?ref=render-ledger"))
        if not eligible_episode(ep,receipt):
            continue
        run_id=str(receipt["run_id"])
        if requested_run_id and run_id!=requested_run_id:
            continue
        actual=api("GET","actions/runs/"+run_id)
        if (actual.get("status") != "completed"
                or actual.get("conclusion") != "failure"):
            continue
        art=api("GET","actions/runs/"+run_id+"/artifacts?per_page=100")
        wanted="daily-preview-"+slug+"-"+run_id
        if (art.get("total_count",0)>100
                or not any(a.get("name")==wanted and
                           a.get("expired") is False and
                           int(a.get("size_in_bytes") or 0)>100_000
                           for a in art.get("artifacts") or [])):
            continue
        return {"episode":slug,"run_id":run_id,"artifact_name":wanted}
    return None


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--requested-run-id",default="")
    args=parser.parse_args()
    tree=github("GET","git/trees/render-ledger?recursive=1")
    if tree.get("truncated"):
        raise RuntimeError("PHONETIC_REPAIR_TRUNCATED_LEDGER")
    catalog=decode_entry(github("GET","contents/cloud-shorts/episodes.json?ref=main"))
    if not isinstance(catalog.get("episodes"),list):
        raise RuntimeError("PHONETIC_REPAIR_MISSING_CATALOG")
    selected=select_one(catalog["episodes"],[
        x["path"] for x in tree.get("tree") or [] if x.get("type")=="blob"],
        requested_run_id=args.requested_run_id)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if not selected:
        args.output.write_text("has_job=false\n",encoding="utf8")
        print("AUTO_PHONETIC_REPAIR_EMPTY")
        return
    args.output.write_text(
        "has_job=true\nfailed_run_id="+selected["run_id"]+
        "\nepisode="+selected["episode"]+
        "\nartifact_name="+selected["artifact_name"]+"\n",encoding="utf8")
    print("AUTO_PHONETIC_REPAIR_SELECTED",selected["episode"],
          selected["run_id"],flush=True)


if __name__=="__main__":
    main()
