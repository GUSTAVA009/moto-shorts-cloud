"""Local fail-closed tests for final mixed MP4 narration check."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import mixed_audio_qa as m


class MixedAudioTests(unittest.TestCase):
    def test_missing_mix_never_passes(self):
        with self.assertRaises(ValueError):
            m.media_audio_present(Path("/nonexistent-gustava-episode.mp4"))

    def test_not_an_mp4_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d)/"not_video.wav"
            f.write_bytes(b"x"*300000)
            with self.assertRaises(ValueError):
                m.media_audio_present(f)

    def test_valid_mp4_is_checked_for_both_audio_and_video(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"video.mp4"
            f.write_bytes(b"x"*300000)
            broken='{"format":{"duration":"15"},"streams":[{"codec_type":"video"}]}'
            with patch.object(m.subprocess, "run") as runner:
                runner.return_value.stdout=broken
                with self.assertRaisesRegex(RuntimeError, "lacks valid"):
                    m.media_audio_present(f)

    def test_matching_audio_and_video_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"video.mp4"
            f.write_bytes(b"x"*300000)
            sample='{"format":{"duration":"16.33"},"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}'
            with patch.object(m.subprocess, "run") as runner:
                runner.return_value.stdout=sample
                self.assertEqual(m.media_audio_present(f), 16.33)


if __name__=="__main__":
    unittest.main()
