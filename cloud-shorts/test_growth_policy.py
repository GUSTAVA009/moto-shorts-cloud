"""Offline tests for monetization math, strategy pivots and sample-size guardrails."""
import unittest
import growth_policy as g


def snapshot(**kwargs):
    o = {"snapshot_date":"2026-10-28", "subscribers":522,
         "eligible_shorts_views_90d":781,
         "eligible_longform_watch_hours_365d":26,
         "shorts_views_28d":2974, "shorts_engaged_views_28d":1300,
         "shorts_subscribers_gained_28d":1,
         "viewed_instead_of_swiped_fraction":.486,
         "shorts_with_48h_data":5}
    o.update(kwargs)
    return o


class GrowthPolicyTests(unittest.TestCase):
    def test_ypp_uses_or_not_and(self):
        r=g.evaluate(snapshot(subscribers=1000,eligible_shorts_views_90d=10_000_000))
        self.assertTrue(r["goals"]["full_ads_qualified"])
        r=g.evaluate(snapshot(subscribers=1000,eligible_longform_watch_hours_365d=4000))
        self.assertTrue(r["goals"]["full_ads_qualified"])
        self.assertFalse(g.evaluate(snapshot(subscribers=999,eligible_shorts_views_90d=10_000_000))["goals"]["full_ads_qualified"])
        self.assertFalse(g.evaluate(snapshot(subscribers=1000,eligible_shorts_views_90d=9_999_999,
                                            eligible_longform_watch_hours_365d=3999))["goals"]["full_ads_qualified"])

    def test_accurate_goal_gaps(self):
        r=g.evaluate(snapshot())["goals"]
        self.assertEqual(r["subscribers_remaining"],478)
        self.assertEqual(r["shorts_remaining"],9_999_219)
        self.assertEqual(r["hours_remaining"],3974)

    def test_hook_rebuild_on_genuine_swipe_issue(self):
        r=g.evaluate(snapshot())["priority_experiments"]
        self.assertIn("HOOK_REBUILD",[x["code"] for x in r])

    def test_hook_no_action_if_too_few_views(self):
        r=g.evaluate(snapshot(shorts_views_28d=25))["priority_experiments"]
        self.assertNotIn("HOOK_REBUILD",[x["code"] for x in r])

    def test_sub_conversion_when_engaged_sample_is_large(self):
        r=g.evaluate(snapshot())["priority_experiments"]
        self.assertIn("SUB_CONVERSION",[x["code"] for x in r])

    def test_do_not_infer_decline_from_unknown_recent_data(self):
        past=snapshot(snapshot_date="2026-10-18",comparable_seven_day_views=1400)
        r=g.evaluate(snapshot(comparable_seven_day_views=400,shorts_with_48h_data=2),past)
        self.assertNotIn("REAL_DROP_PIVOT",[x["code"] for x in r["priority_experiments"]])

    def test_pivot_when_verified_decline_and_enough_shorts(self):
        past=snapshot(snapshot_date="2026-10-18",comparable_seven_day_views=1400)
        curr=snapshot(comparable_seven_day_views=600,shorts_with_48h_data=5)
        r=g.evaluate(curr,past)
        self.assertIn("REAL_DROP_PIVOT",[x["code"] for x in r["priority_experiments"]])

    def test_no_comparing_lifetime_views_to_ypp_views(self):
        curr=snapshot(lifetime_public_views=99999999,eligible_shorts_views_90d=781)
        self.assertEqual(g.evaluate(curr)["goals"]["eligible_shorts_views_90d"],781)

    def test_incomplete_metrics_do_not_crash_or_guess(self):
        r=g.evaluate({"snapshot_date":"2026-10-28","subscribers":522})
        self.assertIsNone(r["goals"]["shorts_remaining"])
        self.assertFalse(r["goals"]["full_ads_qualified"])

    def test_invalid_fractions_rejected(self):
        with self.assertRaisesRegex(ValueError,"0..1"):
            g.evaluate(snapshot(viewed_instead_of_swiped_fraction=47))


if __name__=="__main__":
    unittest.main()
