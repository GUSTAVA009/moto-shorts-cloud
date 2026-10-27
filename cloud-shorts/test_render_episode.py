"""No-network tests for original episode pipeline."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import render_episode as r
import tts_voice as t


class EpisodeTests(unittest.TestCase):
    def test_both_original_episodes_have_distinct_provenance(self):
        data = json.loads((Path(__file__).parent / "episodes.json").read_text(encoding="utf8"))
        self.assertGreaterEqual(len(data["episodes"]), 2)
        slugs = set()
        for ep in data["episodes"]:
            slug = r.validate_episode(ep)
            self.assertNotIn(slug, slugs)
            slugs.add(slug)
            self.assertNotIn("https://", ep["description"])
            self.assertGreater(len(ep["shots"]), 3)

    def test_external_video_urls_rejected(self):
        item = {
            "url": "https://example.com/bad.mp4",
            "source_page": "https://www.pexels.com/video/race-123456/",
        }
        with self.assertRaises(ValueError):
            r.checked_source(item)

    def test_mismatched_pexels_id_rejected(self):
        item = {
            "url": "https://videos.pexels.com/video-files/123456/123456-hd_1080_1920.mp4",
            "source_page": "https://www.pexels.com/video/other-543212/",
        }
        with self.assertRaises(ValueError):
            r.checked_source(item)

    def test_pexels_download_allowed_only_with_matching_id(self):
        item = {
            "url": "https://www.pexels.com/download/video/5803097/",
            "source_page": "https://www.pexels.com/video/forest-5803097/",
        }
        self.assertEqual(r.checked_source(item), "5803097")

    def test_no_banned_words_in_public_fields(self):
        ep = json.loads((Path(__file__).parent / "episodes.json").read_text())["episodes"][0]
        changed = dict(ep, caption_end="ХАПЫЧ навсегда")
        with self.assertRaises(ValueError):
            r.validate_episode(changed)

    def test_original_rain_safety_facts_fit_generated_narration(self):
        import render_episode as r
        import json
        from pathlib import Path
        episodes=json.loads((Path(__file__).parent/"episodes.json").read_text(encoding="utf8"))["episodes"]
        ep=next(x for x in episodes if x["id"]=="wet-road-checklist-08")
        self.assertEqual(r.validate_episode(ep),ep["id"])
        windows=r.fitted_story_beats(ep,15.23)
        self.assertEqual(len(windows),3)
        self.assertEqual([w[0] for w in windows],[x["text"] for x in ep["story_steps"]])
        self.assertTrue(all(w[2]<15.23-2.75 for w in windows))
        self.assertTrue(all(windows[i][2]<windows[i+1][1] for i in range(2)))
        with self.assertRaises(RuntimeError):
            r.fitted_story_beats(ep,8.0)

    def test_description_no_links_even_if_untrusted(self):
        self.assertEqual(r.clean_description("Привет\nhttps://example.org/a\n#shorts"),
                         "Привет\n#shorts")

    def test_voiceover_text_guard(self):
        with patch.object(t, "safe_download") as download:
            with self.assertRaises(ValueError):
                t.render("Коротко", Path("/fake.wav"), Path("/fake"))
            download.assert_not_called()
        self.assertEqual(len(t.MODEL_SHA256), 64)


if __name__ == "__main__":
    unittest.main()
