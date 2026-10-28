"""Offline quality and duplicate guards for Buffer R2 bridge."""
import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest
import buffer_autopublish as b

class BufferBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.video=Path(self.tmp.name)/"example.mp4"
        self.video.write_bytes(b"x"*500000)
        self.episode={"id":"fresh-short-99","auto_publish":True,
                      "footage":[{"license":"Pexels License"}]}
        self.meta={"episode_id":self.episode["id"],"title":"Атмосферная история",
                   "description":"Досмотри до конца."}
        self.voice={"episode_id":self.episode["id"],"status":"passed",
                    "passed":True,"lexical_coverage":.98,
                    "ending_coverage":1,"final_word_present":True}
        self.mixed={"episode_id":self.episode["id"],"source":"FINAL_MIXED_MP4",
                    "status":"passed","passed":True,"lexical_coverage":.97,
                    "ending_coverage":1,"final_word_present":True,
                    "numerics_match":True,
                    "mp4_sha256":b.prior.file_sha256(self.video)}
    def tearDown(self):self.tmp.cleanup()
    def env(self, **changes):
        return patch.dict(b.os.environ,{"YOUTUBE_EXPECTED_CHANNEL_ID":b.CHANNEL,**changes})
    def test_dry_run_offline(self):
        with self.env(),patch.object(b.ledger,"api",side_effect=AssertionError("network")):
            self.assertTrue(b.deliver(self.episode,self.meta,self.voice,self.mixed,self.video,True)["dry_run"])
    def test_refuse_inaccurate_voice(self):
        self.voice["lexical_coverage"]=.80
        with self.env(),self.assertRaisesRegex(ValueError,"95%"):
            b.validate(self.episode,self.meta,self.voice,self.mixed,self.video)
    def test_refuse_inaccurate_final_mix(self):
        self.mixed["lexical_coverage"]=.81
        with self.env(),self.assertRaisesRegex(ValueError,"95%"):
            b.validate(self.episode,self.meta,self.voice,self.mixed,self.video)
    def test_refuse_wrong_channel(self):
        with self.env(YOUTUBE_EXPECTED_CHANNEL_ID="UCaaaaaaaaaaaaaaaaaaaaaa"):
            with self.assertRaisesRegex(ValueError,"Wrong destination"):
                b.validate(self.episode,self.meta,self.voice,self.mixed,self.video)
    def test_no_opt_in_no_network(self):
        with self.env(BUFFER_AUTO_PUBLISH_ENABLED=""),patch.object(b,"upload_r2",side_effect=AssertionError("upload")):
            self.assertIn("skipped",b.deliver(self.episode,self.meta,self.voice,self.mixed,self.video))
    def test_shared_publora_receipts_prevent_duplicates(self):
        settings={"BUFFER_AUTO_PUBLISH_ENABLED":"true","BUFFER_API_KEY":"test",
                  "BUFFER_CHANNEL_ID":"channel_example_123",
                  "R2_ENDPOINT":"https://"+"a"*32+".r2.cloudflarestorage.com",
                  "R2_ACCESS_KEY_ID":"test","R2_SECRET_ACCESS_KEY":"test",
                  "R2_BUCKET":"test","R2_PUBLIC_BASE_URL":"https://cdn.example.org"}
        with self.env(**settings),patch.object(b.ledger,"api",return_value={"sha":"existing"}),patch.object(b,"upload_r2",side_effect=AssertionError("should not upload")):
            self.assertIn("Existing",b.deliver(self.episode,self.meta,self.voice,self.mixed,self.video)["skipped"])
    def test_permanent_public_media_url(self):
        with self.env(R2_PUBLIC_BASE_URL="https://cdn.example.org"):
            self.assertEqual(b.public_url("a"*64),"https://cdn.example.org/gustava-shorts/"+"a"*64+".mp4")
    def test_reject_presigned_r2_url(self):
        with self.env(R2_PUBLIC_BASE_URL="https://cdn.example.org/vid.mp4?X-Amz-Date=2026"):
            with self.assertRaises(ValueError):b.public_url("a"*64)

if __name__=="__main__": unittest.main()
