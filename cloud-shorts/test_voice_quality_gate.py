import unittest
import voice_quality_gate as v


class VoiceGuardTests(unittest.TestCase):
    TEXT="Поворот начинается с наклона. А ты замечал этот эффект?"
    GOOD={"duration_seconds":13.2,"clipped_fraction":0.0,
          "rms_dbfs":-16.0,"peak_dbfs":-4.0,
          "longest_interior_quiet_gap_seconds":.55}

    def test_clear_voice_with_approval_allowed(self):
        r=v.check(self.TEXT,self.TEXT,"unused.wav",True,self.GOOD)
        self.assertTrue(r["publish_allowed"])
        self.assertAlmostEqual(r["text"]["lexical_coverage"],1)

    def test_robotic_voice_not_approved(self):
        r=v.check(self.TEXT,self.TEXT,"unused.wav",False,self.GOOD)
        self.assertFalse(r["publish_allowed"])
        self.assertIn("HUMAN_NATURALNESS_APPROVAL_MISSING",r["hard_errors"])

    def test_missing_final_phrase_blocked(self):
        r=v.check(self.TEXT,"Поворот начинается с наклона.","unused.wav",True,self.GOOD)
        self.assertFalse(r["publish_allowed"])
        self.assertIn("ENDING_MISSING_OR_WRONG",r["hard_errors"])

    def test_too_many_recognition_mismatches(self):
        r=v.check(self.TEXT,"Поворот начинается. А ты замечал этот эффект?","unused.wav",True,self.GOOD)
        self.assertIn("RECOGNITION_BELOW_97_PERCENT",r["hard_errors"])

    def test_digital_clipping_hard_rejected(self):
        r=v.check(self.TEXT,self.TEXT,"unused.wav",True,
                  dict(self.GOOD,clipped_fraction=.04))
        self.assertFalse(r["publish_allowed"])
        self.assertIn("DIGITAL_CLIPPING",r["hard_errors"])

    def test_long_pause_is_review_warning_not_fake_robot_detector(self):
        r=v.check(self.TEXT,self.TEXT,"unused.wav",True,
                  dict(self.GOOD,longest_interior_quiet_gap_seconds=2.0))
        self.assertIn("LONG_INTERNAL_PAUSE_REVIEW",r["review_warnings"])

    def test_yo_normalization_is_supported(self):
        self.assertTrue(v.compare_text("Всё ещё не поздно.","Все еще не поздно.")["last_four_present"])

    def test_empty_pcm_detected_without_real_audio(self):
        with self.assertRaisesRegex(ValueError,"shorter than 1 second"):
            from unittest.mock import patch
            from subprocess import CompletedProcess
            with patch.object(v.subprocess,"run",return_value=CompletedProcess([],0,stdout=b"\x00"*8,stderr=b"")):
                v.audio_features("test.wav")


if __name__=="__main__":unittest.main()
