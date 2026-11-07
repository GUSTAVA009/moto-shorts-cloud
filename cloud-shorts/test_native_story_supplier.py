"""True 2K source stock must be counted before unattended story creation."""
import os
from unittest.mock import patch
import unittest
import autofill_catalog as af
from moto_autocreate import native_source_candidates


def medium(key,profile="4k",creator="cottonbro studio"):
    w,h=(2160,3840) if profile=="4k" else (1440,2560)
    return {
        "key":key,
        "url":"https://www.pexels.com/download/video/5806214/",
        "author":creator,"license":"Pexels License",
        "native_"+profile+"_sha256":"f"*64,
        "native_"+profile+"_bytes":16_000_000,
        "native_"+profile+"_width":w,
        "native_"+profile+"_height":h,
    }


class NativeUnattendedScriptsTests(unittest.TestCase):
    def test_pending_drafts_must_have_native_2k_evidence(self):
        unready={"id":"old-448px","auto_preview":True,
                 "voice_engine":"gustava_selfhosted_qwen3",
                 "footage":[{"key":"clip_0"},{"key":"clip_1"}]}
        good={"id":"real-2k-native","auto_preview":True,
              "voice_engine":"gustava_selfhosted_qwen3",
              "footage":[medium("clip_0"),medium("clip_1","2k",
                                               "Michele Lazzari")]}
        catalog={"episodes":[unready,good]}
        with patch.dict(os.environ,{"GUSTAVA_NATIVE_SOURCE_ONLY":"1",
                                     "GUSTAVA_EXPORT_PROFILE":"2k"}):
            self.assertEqual(af.pending_originals(catalog,set(),autonomous=True),1)
            self.assertEqual(af.pending_originals(catalog,{"real-2k-native"},
                                                  autonomous=True),0)
            self.assertEqual(af.pending_originals(catalog,set(),autonomous=False),2)

    def test_native_source_filter_never_includes_448p_generated_original(self):
        genuine=medium("px_5806214")
        ltx={"key":"gustava-original-sha","license":"LTX OpenRAIL-M",
             "url":"https://84-252-66-87.sslip.io/yt-factory-originals/clips/a.mp4",
             "author":"GUSTAVA Original Video Production"}
        self.assertEqual(native_source_candidates([ltx,genuine],"2k"),[genuine])
        self.assertEqual(native_source_candidates([ltx,genuine],"4k"),[genuine])
        self.assertEqual(native_source_candidates([ltx],"2k"),[])
        self.assertEqual(native_source_candidates([medium("x","2k")],"4k"),[])


if __name__=="__main__":
    unittest.main()
