"""Offline-only regression tests for automated native-resolution source harvesting."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import native_stock_harvester as h


def source(idx="5806214"):
    return {"key":"pexels-"+idx,
            "url":"https://www.pexels.com/download/video/"+idx+"/",
            "source_page":"https://www.pexels.com/video/motocross-riders-"+idx+"/",
            "source_title":"motorcycle riders actually riding offroad",
            "author":"cottonbro studio","license":"Pexels License",
            "topics":["motocross","racing"],"duration":18}


class PinnedNativeStockTests(unittest.TestCase):
    def test_exact_curated_source_and_licence_only(self):
        self.assertEqual(h.source_id(source()),"5806214")
        self.assertIsNone(h.source_id(dict(source(),license="Unknown")))
        self.assertIsNone(h.source_id(dict(source(),author="")))
        self.assertIsNone(h.source_id(dict(source(),url="http://example.com/x")))
        self.assertIsNone(h.source_id(dict(source(),url=source()["url"]+"?token=abc")))
        self.assertIsNone(h.source_id(dict(
            source(),source_page="https://www.pexels.com/video/another-12345/")))

    def test_cannot_claim_high_resolution_based_only_on_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            cached=Path(tmp)/"pexels-5806214.mp4"
            cached.write_bytes(b"0"*1_000_100)
            with patch.object(h,"ffprobe_video",return_value=(448,800,6.7)):
                status,proof=h.verify_one(source(),Path(tmp))
            self.assertTrue(status.startswith("media_probe_failed"))
            self.assertIsNone(proof)
            self.assertFalse(cached.exists())

    def test_real_file_hash_and_native_dimensions_pinned(self):
        with tempfile.TemporaryDirectory() as tmp:
            cached=Path(tmp)/"pexels-5806214.mp4"
            binary=b"R"*1_010_001
            cached.write_bytes(binary)
            with patch.object(h,"ffprobe_video",return_value=(2160,3840,14.3)):
                status,proof=h.verify_one(source(),Path(tmp))
            self.assertEqual(status,"verified_4k")
            self.assertEqual(proof["native_4k_sha256"],
                             hashlib.sha256(binary).hexdigest())
            self.assertEqual(proof["native_4k_bytes"],len(binary))
            self.assertEqual(proof["native_4k_width"],2160)
            self.assertEqual(proof["native_4k_height"],3840)

    def test_genuine_2160x4096_is_native_4k_crop_not_upscale(self):
        with tempfile.TemporaryDirectory() as tmp:
            cached=Path(tmp)/"pexels-5806214.mp4"
            cached.write_bytes(b"Y"*1_100_000)
            with patch.object(h,"ffprobe_video",return_value=(2160,4096,11.2)):
                status,proof=h.verify_one(source(),Path(tmp))
            self.assertEqual(status,"verified_4k")
            self.assertEqual(proof["native_4k_width"],2160)
            self.assertEqual(proof["native_4k_height"],4096)
        with tempfile.TemporaryDirectory() as tmp:
            cached=Path(tmp)/"pexels-5806214.mp4"
            cached.write_bytes(b"Y"*1_100_000)
            with patch.object(h,"ffprobe_video",return_value=(3840,2160,11.2)):
                status,proof=h.verify_one(source(),Path(tmp))
            self.assertTrue(status.startswith("media_probe_failed"))
            self.assertIsNone(proof)

    def test_real_2k_is_accepted_without_fake_4k_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            cached=Path(tmp)/"pexels-5806214.mp4"
            cached.write_bytes(b"X"*1_100_000)
            with patch.object(h,"ffprobe_video",return_value=(1440,2560,8.0)):
                status,proof=h.verify_one(source(),Path(tmp))
            self.assertEqual(status,"verified_2k")
            self.assertIn("native_2k_sha256",proof)
            self.assertNotIn("native_4k_sha256",proof)

    def test_incremental_bank_never_marks_script_as_video(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td)
            bank=home/"pool.json"
            state=home/"status.json"
            bank.write_text(json.dumps({"version":1,"sources":[source()]}))
            cache=home/"cache"
            cache.mkdir()
            (cache/"pexels-5806214.mp4").write_bytes(b"G"*1_100_000)
            with patch.object(h,"POOL",bank),patch.object(h,"STATE",state):
                with patch.object(h,"ffprobe_video",return_value=(2160,3840,7.1)):
                    self.assertEqual(h.harvest(max_files=1,max_checks=1,cache=cache),1)
                report=json.loads(bank.read_text())
                self.assertIn("native_4k_sha256",report["sources"][0])
                self.assertEqual(len(json.loads(state.read_text())["scanned"]),1)
                # Repeated scheduled calls do NOT count previously verified video again.
                self.assertEqual(h.harvest(max_files=1,max_checks=1,cache=cache),0)


if __name__=="__main__":
    unittest.main()
