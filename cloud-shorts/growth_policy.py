#!/usr/bin/env python3
"""Deterministic, evidence-gated YouTube growth strategy. No uploads or APIs.

Accepts privately exported YouTube Studio metrics. Does NOT confuse lifetime
views, recent public views, eligible Shorts views, or long-form watch hours.
No creator secret or Studio snapshot is committed to the repository.
"""
import argparse
from datetime import date
import json
from pathlib import Path

SHORTS_TARGET = 10_000_000
HOURS_TARGET = 4_000
SUBS_TARGET = 1_000


def _number(obj, key):
    value = obj.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError("Expected a non-negative number for " + key)
    return float(value)


def evaluate(current, previous=None):
    """Return ranked experiments. Missing or delayed data never signal a decline."""
    date.fromisoformat(current["snapshot_date"])
    subscribers = _number(current, "subscribers")
    shorts = _number(current, "eligible_shorts_views_90d")
    watch_hours = _number(current, "eligible_longform_watch_hours_365d")
    views_28 = _number(current, "shorts_views_28d")
    engaged_28 = _number(current, "shorts_engaged_views_28d")
    viewed = _number(current, "viewed_instead_of_swiped_fraction")
    retention = _number(current, "average_short_viewed_fraction")
    shorts_subscribers = _number(current, "shorts_subscribers_gained_28d")
    if viewed is not None and viewed > 1:
        raise ValueError("viewed_instead_of_swiped_fraction must be 0..1")
    if retention is not None and retention > 3:
        raise ValueError("average_short_viewed_fraction must be 0..3")
    recs = []
    def add(code, evidence, experiment, test_metric, stop_condition):
        recs.append(dict(code=code, evidence=evidence, experiment=experiment,
                         test_metric=test_metric, stop_condition=stop_condition))
    if (views_28 or 0) >= 500 and viewed is not None and viewed < .55:
        add("HOOK_REBUILD",
            "Only {:.1f}% choose to watch rather than swipe (last 28 days).".format(viewed*100),
            "Create 3 materially different 1.5-second openings: unexpected real footage, a visible challenge, and a counterintuitive question. Keep the body educational and original.",
            "viewed_instead_of_swiped_fraction on comparable Shorts after 48+ hours",
            "Do not rank tests before >=500 shown-in-feed impressions per variant.")
    if (engaged_28 or 0) >= 300 and retention is not None and retention < .65:
        add("PACING_REBUILD",
            "Average viewed fraction {:.0f}% is below exploratory 65% target.".format(retention*100),
            "Remove dead air, put the answer within 5-8 seconds, insert meaningful visual changes, and avoid irrelevant stock footage.",
            "average_viewed_fraction, audience-retention curve and finish-rate",
            "Do not reuse footage merely to increase cuts per minute.")
    if (engaged_28 or 0) >= 800 and shorts_subscribers is not None:
        per_1000 = shorts_subscribers*1000/max(engaged_28,1)
        if per_1000 < 2:
            add("SUB_CONVERSION",
                "Only {:.2f} subscribers per 1,000 engaged Short views.".format(per_1000),
                "Introduce a recurring, recognisable series and a specific reason to subscribe; test a non-intrusive last-second invitation.",
                "subscribers_gained / engaged_views by content format",
                "Reject generic begging or scripted fake engagement.")
    if subscribers is not None and (shorts is not None or watch_hours is not None):
        add("DUAL_FORMAT_YPP",
            "YPP requires >=1000 subscribers AND (>=4000 qualified long-form hours in 365d OR >=10m qualified Shorts views in 90d).",
            "Use original Shorts as discovery; release a substantive 8-12 minute long-form episode weekly. Both formats serve the same channel theme.",
            "qualified long-form hours and qualified Shorts views in YouTube Studio Earn",
            "Never add hours watched in Shorts feed to qualified long-form hours.")
    if previous is not None:
        date.fromisoformat(previous["snapshot_date"])
        recent = _number(current, "comparable_seven_day_views")
        old = _number(previous, "comparable_seven_day_views")
        sample = _number(current, "shorts_with_48h_data")
        if (recent is not None and old is not None and old >= 300 and
                sample is not None and sample >= 3 and recent < old*.7):
            add("REAL_DROP_PIVOT",
                "Comparable 7-day views fell {:.1f}%, across {} mature Shorts.".format(100*(1-recent/old),int(sample)),
                "Pause the underperforming storytelling angle. Test one new format for 3 videos without reuploading existing episodes; compare retention and subscriber conversion.",
                "views per 48-hour-old video + viewed-vs-swiped + engaged views",
                "Do not trigger on incomplete days, fewer than 3 comparable uploads, or under-48h Shorts.")
    goals = {
        "subscribers": subscribers,
        "subscribers_remaining": max(0,int(SUBS_TARGET-subscribers)) if subscribers is not None else None,
        "eligible_shorts_views_90d": shorts,
        "shorts_remaining": max(0,int(SHORTS_TARGET-shorts)) if shorts is not None else None,
        "eligible_longform_watch_hours_365d": watch_hours,
        "hours_remaining": max(0,round(HOURS_TARGET-watch_hours,2)) if watch_hours is not None else None,
        "full_ads_qualified": (
            subscribers is not None and subscribers>=SUBS_TARGET and
            ((shorts is not None and shorts>=SHORTS_TARGET) or
             (watch_hours is not None and watch_hours>=HOURS_TARGET))
        )
    }
    return {"as_of":current["snapshot_date"],"goals":goals,"priority_experiments":recs,
            "data_limitations":[
                "YouTube Studio eligibility metrics may be delayed; use the as-of date.",
                "Public view count is not equivalent to qualified Shorts views.",
                "ASR proves words were understood, not that the voice sounds human.",
                "Improvement is a hypothesis to test, not guaranteed growth."
            ]}


def markdown(report):
    g=report["goals"]
    value=lambda v:"unknown" if v is None else str(v)
    out=["# GUSTAVA Growth Experiments","",
         "Metric snapshot date: "+report["as_of"],"",
         "| YPP metric | Current | Remaining |",
         "|---|---:|---:|",
         "| Subscribers | "+value(g["subscribers"])+" | "+value(g["subscribers_remaining"])+" |",
         "| Qualified Shorts views / 90 days | "+value(g["eligible_shorts_views_90d"])+" | "+value(g["shorts_remaining"])+" |",
         "| Qualified long-form watch hours / 365 days | "+value(g["eligible_longform_watch_hours_365d"])+" | "+value(g["hours_remaining"])+" |","",
         "Eligibility rule: 1000 subscribers AND (4000 long-form hours OR 10 million eligible Shorts views).","",
         "## Ranked experiments"]
    for i,r in enumerate(report["priority_experiments"],1):
        out.extend(["","### "+str(i)+". "+r["code"],
                    "**Evidence:** "+r["evidence"],
                    "**Experiment:** "+r["experiment"],
                    "**Measure:** "+r["test_metric"],
                    "**Gate:** "+r["stop_condition"]])
    out.extend(["","## Limitations"]+["- "+l for l in report["data_limitations"]])
    return "\n".join(out)+"\n"


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--snapshot",type=Path,required=True)
    p.add_argument("--previous",type=Path)
    p.add_argument("--output",type=Path,default=Path("growth-analysis.md"))
    a=p.parse_args()
    obj=lambda f:json.loads(f.read_text(encoding="utf8"))
    r=evaluate(obj(a.snapshot),obj(a.previous) if a.previous else None)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(markdown(r),encoding="utf8")
    a.output.with_suffix(".json").write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding="utf8")
    print("GROWTH_REPORT_READY",str(a.output),"EXPERIMENTS",len(r["priority_experiments"]))


if __name__=="__main__":
    main()
