"""Offline model/license safety checks for Russian audio rendering."""
import unittest
import silero_voice as v


class SileroVoiceTests(unittest.TestCase):
    def test_selected_model_is_commercial_mit_cis_base_only(self):
        self.assertTrue(v.validate_voice())
        self.assertEqual(v.LICENSE_NAME, "MIT")
        self.assertEqual(v.MODEL_ID, "v5_cis_base_nostress")

    def test_unlicensed_models_are_refused(self):
        for model in ("v5_ru", "v5_5_ru", "v5_cis_ext", "v5_cis_ext_nostress"):
            with self.assertRaisesRegex(ValueError, "MIT"):
                v.validate_voice(model_name=model)

    def test_unreviewed_speakers_are_refused(self):
        with self.assertRaises(ValueError):
            v.validate_voice(speaker="ru_unchecked_voice")


if __name__=="__main__":
    unittest.main()
