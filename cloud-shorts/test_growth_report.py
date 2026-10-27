"""Offline revenue arithmetic and audience conversion checks."""
import unittest
from decimal import Decimal
import growth_report as g


class TestGrowthReport(unittest.TestCase):
    def test_dollar_target_short_ads_hypothetical(self):
        self.assertEqual(g.views_for_revenue(5000,"0.02"),250000000)
        self.assertEqual(g.views_for_revenue(5000,"0.05"),100000000)
        self.assertEqual(g.views_for_revenue(5000,"0.10"),50000000)
        with self.assertRaises(ValueError):
            g.views_for_revenue(5000,0)

    def test_no_fake_subscriber_conversions_when_missing(self):
        k=g.funnel({"views":909,"likes":6,"comments":0})
        self.assertEqual(k["like_rate_percent"],0.66)
        self.assertEqual(k["comment_rate_percent"],0)
        self.assertIsNone(k["subscriber_per_1000_engaged"])
        self.assertIsNone(k["share_rate_percent"])

    def test_positive_conversion_based_on_real_engaged_views(self):
        k=g.funnel({"views":1000,"likes":18,"comments":3},subs_from_video=6,engaged_views=400,shares=8)
        self.assertEqual(k["subscriber_per_1000_engaged"],15)
        self.assertEqual(k["share_rate_percent"],0.8)

    def test_report_marks_revenue_eligibility_unknown(self):
        from pathlib import Path
        import json
        data=json.loads((Path(__file__).parent/"growth_baseline.json").read_text(encoding="utf8"))
        result=g.report(data)
        self.assertEqual(result["subscriber_gap"],480)
        self.assertIsNone(result["actual_income_usd"])
        self.assertIsNone(result["ypp_enabled"])
        md=g.markdown(result,data["measured_date"])
        self.assertIn("250 000 000",md)
        self.assertIn("не фактический RPM",md)


if __name__=="__main__":
    unittest.main()
