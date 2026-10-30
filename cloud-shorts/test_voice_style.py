"""No-network and full FFmpeg regression of the masculine GUSTAVA narrator."""
from array import array
from pathlib import Path
import math
import shutil
import tempfile
import unittest
import wave

import voice_style as vs


def generate_synthetic_voice(path, hz=165.0, seconds=4.2):
    rate = vs.SAMPLE_RATE
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        pcm = array("h", [0] * int(seconds * rate))
        for idx in range(len(pcm)):
            time = idx / rate
            envelope = min(1.0, time / .18, (seconds - time) / .18)
            pcm[idx] = int(32767 * .24 * max(0, envelope) *
                           math.sin(2 * math.pi * hz * time))
        wav.writeframes(pcm.tobytes())


def zero_crossing_pitch(wav_path):
    """For synthetic sine only. Not a perceptual voice identity classifier."""
    with wave.open(str(wav_path), "rb") as w:
        rate = w.getframerate()
        start = int(rate * 1.0)
        w.setpos(start)
        samples = array("h")
        samples.frombytes(w.readframes(rate * 2))
        positives = sum(a <= 0 < b for a, b in zip(samples, samples[1:]))
    return positives / (len(samples) / rate)


class DeepMaleNarrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.wav = Path(self.tmp.name) / "narration.wav"
        generate_synthetic_voice(self.wav)

    def tearDown(self):
        self.tmp.cleanup()

    def test_profile_constants_are_not_female_voices(self):
        self.assertEqual(vs.SPEAKER, "dima")
        self.assertEqual(vs.PROFILE_ID, "gustava_male_bass_baritone_v5")
        self.assertEqual(vs.PITCH, .87)
        self.assertGreater(vs.PITCH, .84)
        self.assertLess(vs.PITCH, .90)
        self.assertIn("formant=preserved", vs.FILTER)
        self.assertIn("acompressor=", vs.FILTER)
        self.assertNotIn("asoftclip=", vs.FILTER)
        self.assertNotIn("pan=", vs.FILTER)

    def test_clean_presets_have_distinct_source_pitch_without_saturation(self):
        self.assertEqual(len(vs.VOICE_PRESETS), 3)
        for name,(pid,pitch) in vs.VOICE_PRESETS.items():
            chain=vs.filter_for(pitch)
            self.assertIn("formant=preserved",chain)
            self.assertNotIn("asoftclip",chain)
            self.assertNotIn("haas",chain)
            self.assertNotIn("pan=",chain)
            self.assertIn("loudnorm=",chain)
            self.assertIn("alimiter=",chain)
        self.assertGreater(vs.VOICE_PRESETS["baritone"][1],
                           vs.VOICE_PRESETS["bass_baritone"][1])
        self.assertGreater(vs.VOICE_PRESETS["bass_baritone"][1],
                           vs.VOICE_PRESETS["deep_bass"][1])

    def test_missing_profile_must_block_release(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            vs.validate_report(self.wav)

    def test_pcm_signal_guard(self):
        self.assertGreater(vs.verify_pcm(self.wav)["duration_seconds"], 4)
        with wave.open(str(self.wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(vs.SAMPLE_RATE)
            w.writeframes(b"\x00" * (vs.SAMPLE_RATE * 4 * 2))
        with self.assertRaisesRegex(ValueError, "too little sound"):
            vs.verify_pcm(self.wav)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg missing")
    def test_real_dsp_makes_voice_lower_without_overlaps_or_length_changes(self):
        before_hash = vs.sha256(self.wav)
        before_pitch = zero_crossing_pitch(self.wav)
        duration = vs.apply(self.wav)
        self.assertAlmostEqual(duration, 4.2, delta=.25)
        self.assertNotEqual(vs.sha256(self.wav), before_hash)
        actual_pitch = zero_crossing_pitch(self.wav)
        self.assertGreater(actual_pitch, before_pitch * .83)
        self.assertLess(actual_pitch, before_pitch * .91)
        report = vs.validate_report(self.wav)
        self.assertEqual(report["profile_id"], vs.PROFILE_ID)
        self.assertEqual(report["processed_wav_sha256"], vs.sha256(self.wav))
        self.assertTrue(report["quality_passed"])

        # Deliberate tampering invalidates the style proof and blocks Buffer.
        with self.wav.open("ab") as out:
            out.write(b"uncertified")
        with self.assertRaisesRegex(ValueError, "checksum"):
            vs.validate_report(self.wav)


if __name__ == "__main__":
    unittest.main()
