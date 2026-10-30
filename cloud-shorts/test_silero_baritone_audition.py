import unittest
import silero_baritone_audition as m

class AuditionSafetyTests(unittest.TestCase):
    def test_only_mit_checkpoint_and_preselected_male_voices(self):
        self.assertEqual(m.LICENSE,"MIT")
        self.assertEqual(m.MODEL_ID,"v5_cis_base_nostress")
        for speaker in m.CANDIDATES:
            self.assertTrue(m.check_choice(m.MODEL_ID,speaker))
        for invalid in ["v5_cis_ext","v5_ru","v5_5_ru"]:
            with self.assertRaises(ValueError):
                m.check_choice(invalid,m.CANDIDATES[0])
        with self.assertRaises(ValueError):
            m.check_choice(m.MODEL_ID,"ru_zhadyra")

if __name__=="__main__":
    unittest.main()
