import tempfile,unittest,wave
from pathlib import Path
from audio_accents import create,cover_times

class SfxTests(unittest.TestCase):
    def test_sound_effects_are_distinct_valid_original_mono_pcm(self):
        with tempfile.TemporaryDirectory() as root:
            a,b=Path(root)/"a.wav",Path(root)/"b.wav"
            x=create(a,9.5,style="garage-groove",seed=777,sample_rate=4000)
            y=create(b,9.5,style="race-breakbeat",seed=4,sample_rate=4000)
            self.assertNotEqual(a.read_bytes(),b.read_bytes())
            self.assertGreaterEqual(len(x["events_seconds"]),2)
            self.assertLessEqual(x["peak"],.42)
            self.assertFalse(x["stereo_voice_doubled"])
            with wave.open(str(a),"rb") as f:
                self.assertEqual(f.getnchannels(),1)
                self.assertEqual(f.getnframes(),38000)
                self.assertEqual(f.getsampwidth(),2)

    def test_sfx_outside_safe_video_bounds_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                create(Path(root)/"x.wav",70)
            with self.assertRaises(ValueError):
                create(Path(root)/"x.wav",12,style="copyrighted-sample")

    def test_suggested_covers_from_own_movie_not_competitor(self):
        self.assertEqual(cover_times(20),[2,7.4,13.6])
        self.assertTrue(all(0<t<10 for t in cover_times(9.3)))
        with self.assertRaises(ValueError):
            cover_times(1)

if __name__=="__main__":
    unittest.main()
