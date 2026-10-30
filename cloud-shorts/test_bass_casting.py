import unittest
from bass_casting import MALE_CANDIDATES, MODEL, LICENSE, median_pitch

class BassCastingTests(unittest.TestCase):
    def test_only_real_licensed_distinct_actors(self):
        self.assertEqual(MODEL, "v5_cis_base_nostress")
        self.assertEqual(LICENSE, "MIT")
        self.assertGreaterEqual(len(MALE_CANDIDATES), 6)
        self.assertEqual(len(MALE_CANDIDATES),len(set(MALE_CANDIDATES)))
        self.assertTrue(all(s.startswith("ru_") for s in MALE_CANDIDATES))

    def test_pitch_requires_voiced_signal(self):
        import numpy as np
        self.assertIsNone(median_pitch(np.zeros(24000,dtype="float32")))

    def test_fft_pitch_on_synthetic_male_voice(self):
        import numpy as np
        t=np.arange(24000*3)/24000.
        sig=np.sin(2*np.pi*108*t)*.25
        hz=median_pitch(sig)
        self.assertIsNotNone(hz)
        self.assertTrue(102<hz<115,hz)

if __name__=="__main__":
    unittest.main()
