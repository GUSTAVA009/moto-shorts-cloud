"""Seven owner screenshots: factory must keep these growth requirements forever.

Safety: 100 ideas are research hypotheses, never licensed clips, SHA-pinned
narrations or verified public Shorts. Equal-age and real provenance required.
"""
import json
from pathlib import Path
import unittest

import channel_growth_os as o

ROOT=Path(__file__).resolve().parent
def read(path):
    return json.loads((ROOT/path).read_text("utf8"))

def studio(n=3,shown=600,age_hours=48):
    from datetime import datetime,timedelta,timezone
    base=datetime(2026,10,29,0,0,tzinfo=timezone.utc)
    rows=[]
    for k in range(n):
        p=base-timedelta(hours=k)
        m=p+timedelta(hours=age_hours)
        rows.append({
          "video_id":"video"+str(k).zfill(6),
          "category":"facts",
          "published_at":p.isoformat(),
          "measured_at":m.isoformat(),
          "engaged_views":300+k*100,
          "shown_in_feed":shown,
          "subscribers_gained":2,
          "views":600+k*200,
          "shares":k+1,
          "viewed_instead_of_swiped_fraction":0.63,
          "average_percentage_viewed":0.82
        })
    return {
        "channel_id":o.CHANNEL,"source":"official_youtube_studio_export",
        "observed_date":"2026-11-01","subscribers":533,
        "qualified_shorts_views_90d":10000,
        "qualified_longform_watch_hours_365d":120,
        "per_video_48h":rows,
    }


class SevenPillarsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank=read("channel_idea_bank_100.json")
        cls.public=read("channel_public_snapshot_20261101.json")

    def test_100_unique_honest_original_concepts(self):
        items=o.verify_bank(self.bank)
        self.assertEqual(len(items),100)
        self.assertEqual(len({x["title"].casefold() for x in items}),100)
        self.assertEqual(self.bank["mix"],{"facts":35,"stories":25,
                                           "experiments":25,"spectacle":15})
        self.assertTrue(all(x["publishable"] is False for x in o.next_test_batch(items)))

    def test_slate_keeps_owner_selected_7_5_5_3_and_rights_gate(self):
        p=o.compose(self.public,self.bank)
        slate=p["next_20_editorial_briefs"]
        from collections import Counter
        self.assertEqual(dict(Counter(x["category"] for x in slate)),o.MIX)
        self.assertEqual(len(slate),20)
        self.assertTrue(all(x["needs_fresh_licensed_footage"] for x in slate))
        self.assertTrue(all(x["script_status"]=="concept_not_produced" for x in slate))
        self.assertTrue(p["no_verified_winner_if_insufficient_data"])
        self.assertFalse(p["official_youtube_studio_connected"])
        self.assertFalse(p["safe_to_auto_publish_concept_ideas"])
        self.assertFalse(p["safe_to_auto_rebalance_channel_niche"])

    def test_public_counts_are_not_ypp_or_engaged_views(self):
        p=o.compose(self.public,self.bank)
        self.assertEqual(p["real_public_metadata"]["subscribers"],533)
        self.assertEqual(p["real_public_metadata"]["lifetime_public_views"],80382)
        self.assertIsNone(p["monetization"]["thresholds_met_on_official_snapshot"])
        self.assertFalse(p["monetization"]["official_eligibility_observed"])
        self.assertNotIn("100",str(p["experiment_evidence"]))

    def test_matured_cohort_only_and_real_studio_source(self):
        s=studio()
        r=o.compose(self.public,self.bank,s)
        proof=r["experiment_evidence"]["facts"]
        self.assertEqual(proof["observed_videos"],3)
        self.assertEqual(proof["median_48h_engaged_views"],400)
        self.assertEqual(proof["shown_in_feed"],1800)
        self.assertEqual(proof["subscribers_per_1000_engaged"],5.0)
        self.assertEqual(proof["status"],"observed_not_causal")
        self.assertFalse(r["no_verified_winner_if_insufficient_data"])
        insufficient=studio(n=2)
        self.assertEqual(o.winner_evidence(insufficient)["facts"]["status"],
                         "insufficient_equal_age_sample")
        too_young=studio(age_hours=20)
        self.assertEqual(o.winner_evidence(too_young),{})
        self.assertNotEqual(o.monetization("2026-11-01",s)
                            ["thresholds_met_on_official_snapshot"],True)

    def test_refuses_wrong_channel_fabricated_and_noncomparable_data(self):
        with self.assertRaisesRegex(ValueError,"WRONG_CHANNEL"):
            o.validate_public(dict(self.public,channel_id="not-this-one"))
        with self.assertRaisesRegex(ValueError,"WRONG_CHANNEL"):
            o.validate_studio(dict(studio(),channel_id="other"))
        with self.assertRaisesRegex(ValueError,"WRONG_CHANNEL_OR_PROVENANCE"):
            o.validate_studio(dict(studio(),source="social_media_guess"))
        bad=studio()
        bad["per_video_48h"][0]["engaged_views"]=-42
        with self.assertRaisesRegex(ValueError,"INVALID_engaged_views"):
            o.validate_studio(bad)
        duplicate=studio()
        duplicate["per_video_48h"][1]["video_id"]=duplicate["per_video_48h"][0]["video_id"]
        with self.assertRaisesRegex(ValueError,"DUPLICATE_VIDEO"):
            o.validate_studio(duplicate)

    def test_policy_change_2027_not_mixed_with_old(self):
        old=o.monetization("2026-11-01",None)
        new=o.monetization("2027-02-01",None)
        self.assertEqual(old["full_ads_new_applicant_thresholds"]["qualified_shorts_views_90d"],10_000_000)
        self.assertEqual(new["full_ads_new_applicant_thresholds"]["qualified_shorts_views_90d"],20_000_000)
        self.assertEqual(new["full_ads_new_applicant_thresholds"]["qualified_longform_watch_hours_365d"],8_000)
        self.assertTrue(new["goal_is_not_forecast"])
        self.assertFalse(new["ypp_approval_or_monetization_guaranteed"])

    def test_seven_screenshots_are_permanent_repo_contract(self):
        repo=ROOT.parent
        contract=json.loads((ROOT/"factory_contract.json").read_text("utf8"))
        k=contract["seven_pillars_growth"]
        self.assertEqual(k["source"],"Owner's 7 screenshots, 2026-11-01")
        self.assertFalse(k["auto_niche_change_allowed"])
        self.assertTrue(k["no_engagement_fraud_or_mass_produced_repeat_content"])
        self.assertTrue(k["ideas_are_not_approved_scripts_or_mp4s"])
        self.assertEqual(k["next_twenty_approved_mix"],o.MIX)
        self.assertEqual(k["minimum_videos_per_experiment_group"],3)
        self.assertTrue(k["private_studio_data_never_committed_to_public_repo"])
        self.assertTrue(k["manual_assistant_audio_creation_is_not_factory_operation"]
                        if "manual_assistant_audio_creation_is_not_factory_operation" in k
                        else contract["production"]["manual_assistant_audio_creation_is_not_factory_operation"])
        agents=(repo/"AGENTS.md").read_text("utf8")
        doc=(repo/"docs"/"SEVEN_PILLARS_GROWTH_RU.md").read_text("utf8")
        self.assertIn("SEVEN_PILLARS_GROWTH_RU.md",agents)
        self.assertIn("НЕ ДЕЛАЙ РОЛИКИ ЗА ЗАВОД",agents)
        for i in range(1,8):
            self.assertIn("## "+str(i)+".",doc)
        workflow=(repo/".github/workflows/seven-pillars-growth.yml").read_text("utf8")
        self.assertIn("contents: read",workflow)
        self.assertNotIn("secrets.",workflow)
        self.assertNotIn("buffer-backlog",workflow)

    def test_one_programmatic_report_covers_all_7_pillars(self):
        p=o.compose(self.public,self.bank)
        s=o.markdown(p)
        for title in ("## 1.","## 2.","## 3.","## 4.","## 5.","## 6.","## 7."):
            self.assertIn(title,s)
        self.assertIn("Нет исходников и QA",s)
        self.assertIn("$5 000",s)
        self.assertIn("не подключена",s)


if __name__=="__main__":
    unittest.main()
