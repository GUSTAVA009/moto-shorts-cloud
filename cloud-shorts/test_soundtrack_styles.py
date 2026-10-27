"""Ensure every musical atmosphere is original and not the same waveform."""
from pathlib import Path
import tempfile
import unittest
import wave

from soundtrack import generate, STYLES


class StylesTests(unittest.TestCase):
    def test_unique_synthesized_music_for_night_and_garage(self):
        with tempfile.TemporaryDirectory() as folder:
            p1=Path(folder)/"night.wav"
            p2=Path(folder)/"garage.wav"
            p3=Path(folder)/"night_other_episode.wav"
            generate(p1,4.01,bpm=124,sample_rate=3000,style="night-drive",seed=100)
            generate(p2,4.01,bpm=102,sample_rate=3000,style="garage-groove",seed=200)
            generate(p3,4.01,bpm=124,sample_rate=3000,style="night-drive",seed=101)
            contents=[x.read_bytes() for x in (p1,p2,p3)]
            self.assertEqual(len(set(contents)),3)
            for path in (p1,p2,p3):
                with wave.open(str(path),"rb") as wav:
                    self.assertEqual(wav.getnchannels(),1)
                    self.assertEqual(wav.getnframes(),12030)

    def test_expected_music_styles(self):
        self.assertTrue({"action","night-drive","garage-groove",
                         "race-breakbeat","desert-cinematic"}.issubset(set(STYLES)))

    def test_reject_unknown_or_out_of_range(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"bad.wav"
            with self.assertRaises(ValueError):
                generate(p,5,style="copyrighted-song",sample_rate=3000)
            with self.assertRaises(ValueError):
                generate(p,5,bpm=500,sample_rate=3000)


if __name__ == "__main__":
    unittest.main()
