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
                    "human_narration_approved":True,
                    "ending_coverage":1,"final_word_present":True}
        self.mixed={"episode_id":self.episode["id"],"source":"FINAL_MIXED_MP4",
                    "status":"passed","passed":True,"lexical_coverage":.97,
                    "final_mix_listened":True,
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
        with self.env(),self.assertRaisesRegex(ValueError,"97%"):
            b.validate(self.episode,self.meta,self.voice,self.mixed,self.video)
    def test_refuse_inaccurate_final_mix(self):
        self.mixed["lexical_coverage"]=.81
        with self.env(),self.assertRaisesRegex(ValueError,"97%"):
            b.validate(self.episode,self.meta,self.voice,self.mixed,self.video)
    def test_refuse_unreviewed_narrator(self):
        self.voice["human_narration_approved"]=False
        with self.env(),self.assertRaisesRegex(ValueError,"listening review"):
            b.validate(self.episode,self.meta,self.voice,self.mixed,self.video)

    def test_refuse_unreviewed_final_mp4_audio(self):
        self.mixed["final_mix_listened"]=False
        with self.env(),self.assertRaisesRegex(ValueError,"Final MP4 audio"):
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


    def test_buffer_video_post_has_required_youtube_metadata(self):
        """Buffer must receive video, category, title, and the exact verified channel."""
        import io
        import json
        payloads = []
        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *_): self.close()
        def stub_open(request, timeout=None):
            payloads.append(json.loads(request.data.decode("utf8")))
            return Response(json.dumps({"data":{"createPost":{"post":{"id":"post-id-123"}}}}).encode())
        with self.env(BUFFER_API_KEY="test-do-not-publish"):
            with patch.object(b.urllib.request, "urlopen", side_effect=stub_open):
                post=b.buffer_post("Тестовый ролик","Описание без ссылок",
                    "https://media.example.org/shorts/1.mp4",
                    {"youtube_category_id":"2","ai_generated":False})
        self.assertEqual(post["id"],"post-id-123")
        entry=payloads[0]["variables"]["input"]
        self.assertEqual(entry["channelId"], b.BUFFER_CHANNEL)
        self.assertEqual(entry["text"], "Описание без ссылок")
        self.assertEqual(entry["metadata"]["youtube"]["title"],"Тестовый ролик")
        self.assertEqual(entry["metadata"]["youtube"]["categoryId"],"2")
        self.assertIs(entry["metadata"]["youtube"]["madeForKids"],False)
        self.assertEqual(entry["schedulingType"],"automatic")
        self.assertEqual(entry["mode"],"addToQueue")
        self.assertEqual(entry["assets"][0]["video"]["url"],"https://media.example.org/shorts/1.mp4")

    def test_wrong_buffer_channel_id_is_blocked(self):
        with self.env(BUFFER_API_KEY="unused", BUFFER_CHANNEL_ID="another-channel"):
            with self.assertRaisesRegex(ValueError,"differs"):
                b.buffer_post("Title","Desc","https://media.example.org/example.mp4")

    def test_invalid_youtube_category_is_blocked_before_network(self):
        with self.env(BUFFER_API_KEY="unused"),patch.object(b.urllib.request,"urlopen",
                    side_effect=AssertionError("No network allowed")):
            with self.assertRaisesRegex(ValueError,"category"):
                b.buffer_post("Title","Desc","https://media.example.org/example.mp4",
                              {"youtube_category_id":"not-a-category"})

    def test_full_queue_skips_without_reserving_or_uploading(self):
        settings={"BUFFER_AUTO_PUBLISH_ENABLED":"true","BUFFER_API_KEY":"unused",
                  "R2_ENDPOINT":"https://"+"a"*32+".r2.cloudflarestorage.com",
                  "R2_ACCESS_KEY_ID":"test","R2_SECRET_ACCESS_KEY":"test",
                  "R2_BUCKET":"test","R2_PUBLIC_BASE_URL":"https://cdn.example.org"}
        with self.env(**settings),patch.object(b.ledger,"api",return_value=None),\
             patch("buffer_readiness.inspect",return_value={"queue_has_room":False}),\
             patch.object(b.prior,"record",side_effect=AssertionError("no reservation")),\
             patch.object(b,"upload_r2",side_effect=AssertionError("no upload")):
            result=b.deliver(self.episode,self.meta,self.voice,self.mixed,self.video)
        self.assertIn("full",result["skipped"])

if __name__=="__main__": unittest.main()
