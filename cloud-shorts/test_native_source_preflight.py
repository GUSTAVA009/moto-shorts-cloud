"""Native pixel provenance before selecting 2K/4K production MP4."""
import unittest
from native_source_preflight import source_proof, require_native_sources


def source(profile="4k", key="clip_0"):
    dim=(2160,3840) if profile=="4k" else (1440,2560)
    return {
       "key":key,
       "url":"https://www.pexels.com/download/video/5806214/",
       "source_page":"https://www.pexels.com/video/motocross-riders-5806214/",
       "license":"Pexels License",
       "author":"cottonbro studio",
       "native_"+profile+"_sha256":"a"*64,
       "native_"+profile+"_bytes":45_000_000,
       "native_"+profile+"_width":dim[0],
       "native_"+profile+"_height":dim[1],
    }


class NativeSourcePreflightTests(unittest.TestCase):
    def test_actual_pinned_native_4k_works_for_both_profiles(self):
        for profile in ("2k","4k"):
            self.assertEqual(
                source_proof(source(),profile)["width"],2160)
            self.assertEqual(len(require_native_sources({
                "footage":[source(key="clip_0"),source(key="clip_1")]
            },profile)),2)

    def test_2160x4096_real_pixels_crop_to_exact_4k(self):
        media=dict(source(),native_4k_height=4096)
        result=source_proof(media,"4k")
        self.assertEqual((result["width"],result["height"]),(2160,4096))
        # Landscape UHD and nominally high-res narrow clips cannot yield
        # real 2160x3840 pixels after 9:16 cropping.
        with self.assertRaisesRegex(ValueError,"PIXELS_NOT_PROVEN"):
            source_proof(dict(media,native_4k_width=3840,native_4k_height=2160))
        with self.assertRaisesRegex(ValueError,"PIXELS_NOT_PROVEN"):
            source_proof(dict(media,native_4k_width=1080,native_4k_height=4096))

    def test_exact_2k_is_usable_only_for_2k_profile(self):
        self.assertEqual(source_proof(source("2k"))["width"],1440)
        with self.assertRaisesRegex(ValueError,"NATIVE_4K_SOURCE_REQUIRED"):
            source_proof(source("2k"),"4k")

    def test_unverified_448x800_original_is_not_fake_upscaled(self):
        media={"key":"clip_0",
               "url":"https://84-252-66-87.sslip.io/yt-factory-originals/clips/abc.mp4",
               "license":"LTX OpenRAIL-M","author":"GUSTAVA Original Video Production",
               "generation_model":"ltxv-2b-0.9.8-distilled-fp8",
               "duration":6.706}
        with self.assertRaises(ValueError):
            source_proof(media)

    def test_missing_and_ambiguous_native_evidence_rejected(self):
        media=source()
        for key in ("native_4k_bytes","native_4k_sha256","native_4k_height"):
            short=dict(media)
            short.pop(key)
            with self.assertRaises(ValueError):
                source_proof(short)
        both=dict(media,**{
           "native_2k_sha256":"b"*64,
           "native_2k_bytes":18_000_000,
           "native_2k_width":1440,
           "native_2k_height":2560,
        })
        with self.assertRaisesRegex(ValueError,"AMBIGUOUS"):
            source_proof(both)

    def test_evidence_must_match_exact_real_portrait(self):
        for key,bad in (("native_4k_width",1080),
                        ("native_4k_height",1920),
                        ("native_4k_bytes",10),
                        ("native_4k_sha256","0"*63)):
            case=dict(source(),**{key:bad})
            with self.assertRaises(ValueError):
                source_proof(case)

    def test_no_unverified_license_or_unapproved_host_or_extra_source(self):
        for key,bad in (("license","Unknown"),("author",""),
                        ("url","http://example.com/original.mp4"),
                        ("key","clip_2")):
            case=dict(source(),**{key:bad})
            with self.assertRaises(ValueError):
                source_proof(case)

    def test_video_must_have_two_distinct_pinned_source_entries(self):
        with self.assertRaisesRegex(ValueError,"TWO_ACTION_SCENES"):
            require_native_sources({"footage":[source()]})
        with self.assertRaisesRegex(ValueError,"SOURCE_PROOF_MISSING"):
            require_native_sources({"footage":[source(),{
               "key":"clip_1","license":"Pexels License","author":"Owner",
               "url":"https://www.pexels.com/download/video/123/"}]})


if __name__=="__main__":
    unittest.main()
