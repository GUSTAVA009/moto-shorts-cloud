"""Independent hard pixel gates for GUSTAVA @gustava009 production uploads."""
import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
import production_quality as q

class NativeQualityTests(unittest.TestCase):
    def test_portrait_crop_rejects_landscape_4k_fake_vertical_2k(self):
        self.assertEqual(q.available_portrait_crop(3840,2160),(1215,2160))
        self.assertEqual(q.available_portrait_crop(448,800),(448,796))
        self.assertEqual(q.available_portrait_crop(2160,3840),(2160,3840))

    def test_source_real_native_pixel_requirements(self):
        with patch.object(q,"visual_dimensions",return_value=(448,800)):
            with self.assertRaisesRegex(ValueError,"NO_FAKE_UPSCALE"):
                q.require_native_source(Path("lowres.mp4"))
        with patch.object(q,"visual_dimensions",return_value=(1440,2560)):
            self.assertEqual(q.require_native_source(Path("native2k.mp4")),(1440,2560))
            with self.assertRaisesRegex(ValueError,"NO_FAKE_UPSCALE"):
                q.require_native_source(Path("native2k.mp4"),2160,3840)

    def test_public_native_2k_or_4k_only(self):
        with patch.object(q,"visual_dimensions",return_value=(720,1280)):
            with self.assertRaisesRegex(ValueError,"FINAL_SHORTS_2K_OR_4K_REQUIRED"):
                q.require_native_final(Path("fake_720p.mp4"))
        for dims in ((1440,2560),(2160,3840)):
            with patch.object(q,"visual_dimensions",return_value=dims):
                self.assertEqual(q.require_native_final(Path("ok.mp4")),dims)

    def test_profile_is_explicit(self):
        self.assertEqual(q.export_dimensions("2k"),(1440,2560))
        self.assertEqual(q.export_dimensions("4k"),(2160,3840))
        with self.assertRaises(ValueError):
            q.export_dimensions("720p")

if __name__=="__main__":
    unittest.main()
