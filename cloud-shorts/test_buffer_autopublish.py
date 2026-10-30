"""Offline regression tests for the Buffer distribution safety gates."""
import os
import hashlib
from deep_voice import PUBLIC_ATTRIBUTION
from pathlib import Path
import tempfile
import unittest
from unittest.mock import call, patch

import buffer_autopublish as b
from publication_safety import file_sha256


class BufferPublisherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.video = Path(self.tmp.name) / "new-original-22.mp4"
        self.video.write_bytes(b"X" * 200_000)
        self.ep = {"id": "new-original-22", "auto_publish": True,
                   "voice_engine": "aidocmaker_deep",
                   "title": "Мотоцикл на трассе",
                   "narration": "Мотоцикл проходит крутой поворот.",
                   "editorial": {"bike": "offroad-trail-motorcycle"},
                   "footage": [{"license": "Pexels License"}]}
        self.ep["deep_audio"] = {"provider":"aidocmaker.com", "voice_id":"deep",
          "preview_url":"https://storage.googleapis.com/adm--audio-playback--7d--public/mcp-preview/59b382df-d33f-45d2-943d-22f1db747299.mp3",
          "transcript_sha256":hashlib.sha256(self.ep["narration"].encode()).hexdigest(),
          "source_audio_sha256":"a"*64}
        self.meta = {"episode_id": self.ep["id"],
                     "title": "Оригинальный ролик о мотоциклах",
                     "description": "Русский новый сценарий и оригинальный монтаж.\n\n" + PUBLIC_ATTRIBUTION}
        self.voice = {"episode_id": self.ep["id"], "passed": True,
                      "status": "passed", "lexical_coverage": .99,
                      "ending_coverage": 1.0, "final_word_present": True,
                      "voice_profile": "gustava_create_audio_deep_v1", "male_voice_verified": True,
            "voice_speaker": "deep", "voice_provider":"aidocmaker.com",
            "voice_source_audio_sha256":"a"*64}
        self.mix = {"episode_id": self.ep["id"], "source": "FINAL_MIXED_MP4",
                    "passed": True, "status": "passed",
                    "lexical_coverage": .99, "ending_coverage": 1.0,
                    "final_word_present": True, "numerics_match": True,
                    "mp4_sha256": file_sha256(self.video)}

    def tearDown(self):
        self.tmp.cleanup()

    def test_without_global_optin_no_remote_side_effects(self):
        with patch.dict(os.environ, {"BUFFER_AUTO_PUBLISH_ENABLED": ""}):
            with patch.object(b.ledger, "api", side_effect=AssertionError("No API")):
                result = b.publish(self.ep, self.video, self.meta, self.voice, self.mix)
        self.assertIn("disabled", result["skipped"])

    def test_wrong_or_unapproved_voice_is_blocked(self):
        with patch.dict(os.environ, {"BUFFER_AUTO_PUBLISH_ENABLED": "true"}):
            self.ep["voice_engine"] = "silero_cis_base_mit"
            with patch.object(b.ledger, "api", side_effect=AssertionError("No API")):
                result = b.publish(self.ep, self.video, self.meta, self.voice, self.mix)
        self.assertIn("not approved", result["skipped"])

    def test_old_publora_receipt_prevents_duplicate(self):
        with patch.dict(os.environ, {"BUFFER_AUTO_PUBLISH_ENABLED": "true"}):
            with patch.object(b.ledger, "api", side_effect=[None, {"sha": "old"}]):
                with patch.object(b, "buffer", side_effect=AssertionError("Do not post")):
                    result = b.publish(self.ep, self.video, self.meta, self.voice, self.mix)
        self.assertIn("already", result["skipped"])

    def test_bad_final_mp4_checksum_blocks_before_upload(self):
        self.mix["mp4_sha256"] = "0" * 64
        with patch.dict(os.environ, {"BUFFER_AUTO_PUBLISH_ENABLED": "true"}):
            with patch.object(b.ledger, "api", return_value=None):
                with patch.object(b, "release_url", side_effect=AssertionError("No release")):
                    with self.assertRaisesRegex(ValueError, "does not match"):
                        b.publish(self.ep, self.video, self.meta, self.voice, self.mix)

    def test_queue_limit_blocks_release_upload(self):
        with patch.dict(os.environ, {"BUFFER_AUTO_PUBLISH_ENABLED": "true"}):
            with patch.object(b.ledger, "api", return_value=None):
                with patch.object(b, "validate_video", return_value=None):
                    with patch.object(b, "verify_channel", return_value=([{}] * 10, [])):
                        with patch.object(b, "release_url", side_effect=AssertionError("No release")):
                            result = b.publish(self.ep, self.video, self.meta, self.voice, self.mix)
        self.assertIn("near capacity", result["skipped"])

    def test_post_result_rejection_keeps_reservation_and_never_retries(self):
        with patch.dict(os.environ, {"BUFFER_AUTO_PUBLISH_ENABLED": "true"}):
            with patch.object(b.ledger, "api", return_value=None):
                with patch.object(b.ledger, "store") as store:
                    with patch.object(b, "validate_video", return_value=None):
                        with patch.object(b, "verify_channel", return_value=([], [])):
                            with patch.object(b, "release_url", return_value="https://example.com/new.mp4"):
                                with patch.object(b, "buffer", return_value={"createPost": {"message": "invalid"}}) as req:
                                    with self.assertRaisesRegex(RuntimeError, "rejected or uncertain"):
                                        b.publish(self.ep, self.video, self.meta, self.voice, self.mix)
        self.assertEqual(store.call_count, 1)
        self.assertEqual(req.call_count, 1)  # one actual write, no blind retry

    def test_verify_channel_includes_real_buffer_error_status(self):
        valid = {"channel":{"id":b.CHANNEL,"service":"youtube","serviceId":b.YOUTUBE,
                             "isQueuePaused":False,"isDisconnected":False},
                 "scheduledPosts":{"edges":[],"pageInfo":{"hasNextPage":False}},
                 "sentPosts":{"edges":[],"pageInfo":{"hasNextPage":False}},
                 "errorPosts":{"edges":[{"node":{"id":"failed-post","status":"error"}}],
                               "pageInfo":{"hasNextPage":False}},
                 "sendingPosts":{"edges":[],"pageInfo":{"hasNextPage":False}}}
        with patch.object(b,"buffer",return_value=valid) as req:
            queue,sent,errors,sending=b.verify_channel(include_sent=True,include_errors=True)
        self.assertEqual((queue,sent,sending),([],[],[]))
        self.assertEqual(errors[0]["id"],"failed-post")
        self.assertIn("status:[error]",req.call_args.args[0])
        self.assertIn("status:[sending]",req.call_args.args[0])
        self.assertIn("dueAt:{start:",req.call_args.args[0])
        self.assertNotIn("startDate:",req.call_args.args[0])

    def test_youtube_disclosure_only_when_material_realistic_ai_is_present(self):
        # Generic narration + licensed real footage + deterministic music
        # should not force YouTube's visible AI content marker.
        self.assertIs(b.should_disclose_generated_content(self.ep), False)
        for key in ("realistic_synthetic_visuals", "altered_real_event",
                    "impersonates_real_person", "ai_generated_music_main_focus",
                    "ai_disclosure_required"):
            e = dict(self.ep, **{key: True})
            with self.subTest(key=key):
                self.assertIs(b.should_disclose_generated_content(e), True)
        unknown = dict(self.ep, voice_engine="unknown_new_video_model")
        self.assertIs(b.should_disclose_generated_content(unknown), True)
        no_provenance = dict(self.ep, footage=[{"license": "unknown"}])
        self.assertIs(b.should_disclose_generated_content(no_provenance), True)

    def test_valid_post_uses_correct_channel_and_youtube_metadata(self):
        with patch.dict(os.environ, {"BUFFER_AUTO_PUBLISH_ENABLED": "true"}):
            with patch.object(b.ledger, "api", side_effect=[None, None, {"sha": "receiptsha"}]):
                with patch.object(b.ledger, "store") as store:
                    with patch.object(b, "validate_video", return_value=None):
                        with patch.object(b, "verify_channel", return_value=([], [])):
                            with patch.object(b, "release_url", return_value="https://example.com/ready.mp4"):
                                with patch.object(b, "buffer", return_value={
                                    "createPost": {"post": {"id": "post1", "channelId": b.CHANNEL,
                                                           "dueAt": "2026-10-30T10:00:00Z"}}}) as req:
                                    result = b.publish(self.ep, self.video, self.meta, self.voice, self.mix)
        self.assertTrue(result["queued"])
        self.assertEqual(store.call_count, 2)
        posted = req.call_args.args[1]["input"]
        self.assertEqual(posted["channelId"], b.CHANNEL)
        self.assertEqual(posted["metadata"]["youtube"]["categoryId"], "2")
        self.assertIs(posted["metadata"]["youtube"]["isAiGenerated"], False)
        self.assertIs(posted["aiAssisted"], True)  # honest AI scripting assistance
        self.assertTrue(posted["assets"][0]["video"]["url"].startswith("https://"))
        self.assertFalse(posted.get("saveToDraft", False))
        self.assertEqual(posted["mode"], "customScheduled")
        self.assertTrue(posted["dueAt"].endswith("Z"))


if __name__ == "__main__":
    unittest.main()
