"""Regression guard for the measured GUSTAVA DEEP Shorts stereo loudness fix.

The real rain-city DEEP pilot measured roughly -24.9 LUFS / -8.3 dBTP;
post-mix +6 dB with peak limiting produced -18.2 LUFS / -1.7 dBTP.
The gain must be AFTER the single approved DEEP voice and stereo bed mix.
"""
from pathlib import Path
import unittest


SOURCE = (Path(__file__).resolve().parent / "render_episode.py").read_text(
    encoding="utf8"
)


class DeepStereoMasterTests(unittest.TestCase):
    def test_final_master_raises_both_channels_after_mix(self):
        self.assertIn(
            "[ducked][voice_mix]amix=inputs=2:duration=first:normalize=0,",
            SOURCE,
        )
        self.assertIn(
            '"volume=6dB,alimiter=limit=0.92[a]"',
            SOURCE,
        )

    def test_voice_has_only_one_main_audio_feed(self):
        # voice_duck controls the music duck; voice_mix is the single audible
        # narrator. Mastering must not introduce another timed or shifted
        # narrator copy in the other stereo channel.
        self.assertIn(
            "aformat=channel_layouts=stereo,asplit=2[voice_duck][voice_mix]",
            SOURCE,
        )
        self.assertNotIn("adelay=160|320", SOURCE)


if __name__ == "__main__":
    unittest.main()
