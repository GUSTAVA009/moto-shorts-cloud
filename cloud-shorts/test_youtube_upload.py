#!/usr/bin/env python3
"""Offline tests: do not access Google, publish, or require secrets."""
import json
import unittest
import os
import tempfile
from pathlib import Path

import youtube_upload as yt

class DirectUploadTests(unittest.TestCase):
    def test_remove_source_urls_and_attribution(self):
        original = ("Выехал на 5 минут! 😅\n"
                    "Видео: cottonbro studio / Pexels. Монтаж и русская озвучка.\n"
                    "https://www.pexels.com/video/123/\n#мото #shorts")
        result = yt.clean_description(original)
        self.assertIn("Выехал", result)
        self.assertIn("#shorts", result)
        self.assertNotIn("https://", result)
        self.assertNotIn("Pexels", result)

    def test_metadata_private_default(self):
        meta = {"title":"Сложный подъём! #shorts",
                "description":"А ты бы рискнул?"}
        data = yt.build_body(meta,"private")
        self.assertEqual(data["status"]["privacyStatus"],"private")
        self.assertFalse(data["status"]["selfDeclaredMadeForKids"])
        self.assertEqual(data["snippet"]["categoryId"],"2")

    def test_reject_bad_title_and_tags(self):
        with self.assertRaises(ValueError):
            yt.build_body({"title":"x","description":"Текст"},"private")
        with self.assertRaises(ValueError):
            yt.build_body({"title":"Это заголовок","description":"Текст","tags":4},"private")

    def test_preflight_without_google(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            video=root/"test.mp4"
            video.write_bytes(b"12345"*21000)
            meta=root/"publication.json"
            meta.write_text(json.dumps({"title":"Покатушка на мото","description":"Описание"}),encoding="utf8")
            body,fingerprint=yt.preflight(video,meta,"private")
            self.assertEqual(len(fingerprint),64)
            self.assertEqual(body["snippet"]["title"],"Покатушка на мото")

    def test_channel_is_mandatory(self):
        with self.assertRaises(RuntimeError):
            yt.required_env("__THIS_CHANNEL_IS_NOT_CONFIGURED_IN_TEST__")

if __name__=="__main__":
    unittest.main()
