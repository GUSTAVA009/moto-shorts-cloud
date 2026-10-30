import unittest
from voice_quality_probe import PHRASES,best_candidate

class ProbeSafetyTests(unittest.TestCase):
    def test_candidates_are_unbranded_safe_and_not_reused(self):
        self.assertGreaterEqual(len(PHRASES),8)
        self.assertEqual(sum(x.startswith('track_') for x in PHRASES),4)
        self.assertEqual(sum(x.startswith('repair_') for x in PHRASES),4)
        self.assertEqual(len(set(PHRASES.values())),len(PHRASES))
        for text in PHRASES.values():
            self.assertTrue(120<=len(text)<=350)
            self.assertNotIn("хапыч",text.casefold())
            self.assertNotIn("эндуро",text.casefold())

    def test_never_choose_failed_asr(self):
        self.assertIsNone(best_candidate([{"passed":False,"lexical_coverage":0.99}]))
        good={"id":"good","passed":True,"lexical_coverage":1.0,"beginning_coverage":1.0,
              "ending_coverage":1.0,"duration_seconds":14}
        bad={"id":"bad","passed":False,"lexical_coverage":1.0,"beginning_coverage":1.0,
              "ending_coverage":1.0,"duration_seconds":13}
        self.assertEqual(best_candidate([bad,good])["id"],"good")

if __name__=="__main__":
    unittest.main()
