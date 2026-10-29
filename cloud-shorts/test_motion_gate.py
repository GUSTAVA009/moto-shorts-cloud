"""Motion and stereo regression tests without network or actual video downloads."""
import json
from pathlib import Path
from unittest.mock import Mock, patch
import subprocess
import unittest

import render_episode
import buffer_autopublish


class FreezeAndAudioTests(unittest.TestCase):
    @patch("render_episode.subprocess.run")
    def test_static_clip_is_rejected_before_concat(self, run):
        run.return_value = Mock(returncode=0, stderr="lavfi.freezedetect.freeze_start: 0\n")
        self.assertFalse(render_episode.motion_verified(Path("some-scene.mp4")))

    @patch("render_episode.subprocess.run")
    def test_moving_clip_can_be_concatenated(self, run):
        run.return_value = Mock(returncode=0, stderr="frame=64 fps=0.0")
        self.assertTrue(render_episode.motion_verified(Path("moving-scene.mp4")))

    @patch("render_episode.subprocess.run")
    def test_unavailable_motion_check_fails_closed(self, run):
        run.return_value = Mock(returncode=1, stderr="ffmpeg failed")
        with self.assertRaisesRegex(RuntimeError, "motion QA"):
            render_episode.motion_verified(Path("bad.mp4"))

    @patch("buffer_autopublish.subprocess.run")
    def test_mono_final_video_is_never_published(self, run):
        probe = {"format": {"duration": "20.0"}, "streams": [
            {"codec_type": "video", "width": 720, "height": 1280,
             "avg_frame_rate": "30/1", "nb_read_frames": "600", "duration": "20.0"},
            {"codec_type": "audio", "channels": 1}]}
        run.return_value = Mock(returncode=0, stdout=json.dumps(probe))
        with self.assertRaisesRegex(RuntimeError, "stereo"):
            buffer_autopublish.validate_video(Path("mono.mp4"))

    @patch("buffer_autopublish.subprocess.run")
    def test_stereo_moving_final_video_is_accepted(self, run):
        probe = {"format": {"duration": "20.0"}, "streams": [
            {"codec_type": "video", "width": 720, "height": 1280,
             "avg_frame_rate": "30/1", "nb_read_frames": "600", "duration": "20.0"},
            {"codec_type": "audio", "channels": 2}]}
        run.side_effect = [Mock(returncode=0, stdout=json.dumps(probe)),
                           Mock(returncode=0, stderr="frame=600 no frozen region")]
        buffer_autopublish.validate_video(Path("stereo.mp4"))
        self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
