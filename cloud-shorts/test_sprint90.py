"""Offline 90-day YouTube Earn sprint math; no paid services or fake views."""
import json
from pathlib import Path
import unittest
import sprint90

class Sprint90Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b=json.loads((Path(__file__).parent/"growth_baseline.json").read_text(encoding="utf8"))

    def test_exact_official_earn_counters(self):
        m=sprint90.required_metrics(self.b,90,45)
        self.assertEqual(m["subscriber_gap"],480)
        self.assertEqual(m["qualified_shorts_current_asof"],780)
        self.assertEqual(m["qualified_shorts_gap"],9_999_220)
        self.assertEqual(m["shorts_daily_required_scenario"],111_103)
        self.assertEqual(m["shorts_average_per_new_upload_scenario"],222_205)
        self.assertEqual(m["longform_hours_gap"],3973)
        self.assertEqual(m["longform_views_if_5_minutes_average"],47676)
        self.assertEqual(m["earn_progress_data_as_of"],"2026-10-22")

    def test_2fa_verified_and_region_still_unverified(self):
        m=sprint90.required_metrics(self.b)
        self.assertTrue(m["two_step_verification_complete"])  # Verified by YouTube Studio Earn on 2026-10-28
        self.assertFalse(m["payments_country_verified"])
        self.assertFalse(m["ypp_approved"])

    def test_public_views_not_counted_as_qualified(self):
        b=json.loads(json.dumps(self.b))
        b["last_public_short"]["views"]=90_000_000
        m=sprint90.required_metrics(b)
        self.assertEqual(m["qualified_shorts_gap"],9_999_220)

    def test_period_assumptions_validated(self):
        with self.assertRaises(ValueError):
            sprint90.required_metrics(self.b,0,45)
        with self.assertRaises(ValueError):
            sprint90.required_metrics(self.b,90,0)

    def test_report_warns_not_to_copy_other_creators(self):
        m=sprint90.required_metrics(self.b)
        text=sprint90.markdown(self.b,m,90,45)
        self.assertIn("скользящие 90 дней",text)
        self.assertIn("Не копировать чужую подборку",text)
        self.assertIn("2-step",sprint90.recommendations(m)[0].lower())

if __name__=="__main__":
    unittest.main()
