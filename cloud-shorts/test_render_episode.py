"""No-network tests for original episode pipeline."""
import json
from pathlib import Path
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import render_episode as r
import tts_voice as t


class EpisodeTests(unittest.TestCase):
    def test_replacement_helmet_uses_real_bright_moving_licensed_source(self):
        data = json.loads((Path(__file__).parent / "episodes.json").read_text(encoding="utf8"))
        ep = next(e for e in data["episodes"] if e["id"] == "gustava-20-f01-20261030")
        source = next(m for m in ep["footage"] if m["key"] == "clip_1")
        cut = next(s for s in ep["shots"] if s["source"] == "clip_1")
        self.assertTrue(source["source_page"].endswith("/woman-wearing-a-helmet-9606781/"))
        self.assertEqual(source["duration"], 21)
        self.assertEqual(source["license"], "Pexels License")
        self.assertLessEqual(r.required_source_seconds(ep, "clip_1"), source["duration"])
        self.assertGreaterEqual(sum(s["seconds"] for s in ep["shots"]), 12)
        self.assertEqual(ep["source_revision_reason"], "frozen_source_replaced")
        self.assertNotIn("28209492", str(ep["footage"]))
        self.assertNotIn("12405712", str(ep["footage"]))
        self.assertFalse(ep["auto_publish"])

    def test_cyrillic_video_titling_never_renders_missing_emoji_as_tofu(self):
        original="ПЕРВЫЙ ВЫЕЗД: улыбка или скорость? 🏍️"
        clean=r.safe_caption_display(original)
        self.assertEqual(clean,"ПЕРВЫЙ ВЫЕЗД: улыбка или скорость?")
        self.assertNotIn("🏍",clean)
        self.assertEqual(r.safe_caption_display("ДВА РАЗНЫХ МОМЕНТА"),
                         "ДВА РАЗНЫХ МОМЕНТА")

    def test_both_original_episodes_have_distinct_provenance(self):
        data = json.loads((Path(__file__).parent / "episodes.json").read_text(encoding="utf8"))
        self.assertGreaterEqual(len(data["episodes"]), 2)
        slugs = set()
        for ep in data["episodes"]:
            slug = r.validate_episode(ep)
            self.assertNotIn(slug, slugs)
            slugs.add(slug)
            self.assertNotIn("https://", ep["description"])
            self.assertGreater(len(ep["shots"]), 1)

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
            "author": "Verified contributor", "license": "Pexels License",
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

    def test_large_pexels_source_is_streamed_not_downloaded_whole(self):
        item = {"key":"clip_0","url":"https://www.pexels.com/download/video/33987059/",
                "source_page":"https://www.pexels.com/video/forest-motorcycle-33987059/",
                "license":"Pexels License","author":"Original Creator","duration":36}
        calls = []
        def ffmpeg_stub(cmd, **kwargs):
            calls.append(cmd)
            Path(cmd[-1]).write_bytes(b"\x00" * 500_000)
            return SimpleNamespace(returncode=0,stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            dst=Path(tmp)/"pexels.mp4"
            with patch.object(r.subprocess,"run",side_effect=ffmpeg_stub), \
                 patch.object(r,"probe",return_value=(14.0,[{"codec_type":"video"}])), \
                 patch.object(r.urllib.request,"urlopen",side_effect=AssertionError("Never load 4K source fully")):
                r.download(item,dst,required_seconds=13.5)
            self.assertEqual(dst.stat().st_size,500_000)
        self.assertEqual(len(calls),1)
        self.assertIn("-t",calls[0])
        self.assertEqual(calls[0][calls[0].index("-t")+1],"13.50")
        self.assertEqual(calls[0][calls[0].index("-i")+1],item["url"])

    def test_bounded_download_rejects_incomplete_or_fake_clips(self):
        item = {"key":"clip_1","url":"https://www.pexels.com/download/video/32918034/",
                "source_page":"https://www.pexels.com/video/forest-motorcycle-32918034/",
                "license":"Pexels License","author":"Verified Creator","duration":67}
        def ffmpeg_stub(cmd,**kwargs):
            Path(cmd[-1]).write_bytes(b"a"*500_000)
            return SimpleNamespace(returncode=0,stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            dst=Path(tmp)/"not-ready.mp4"
            with patch.object(r.subprocess,"run",side_effect=ffmpeg_stub), \
                 patch.object(r,"probe",return_value=(8.0,[{"codec_type":"video"}])):
                with self.assertRaisesRegex(RuntimeError,"missing required scene time"):
                    r.download(item,dst,required_seconds=13.0)
            self.assertFalse(dst.exists())
            self.assertFalse((Path(tmp)/"not-ready.source.tmp.mp4").exists())

    def test_small_genuine_moving_excerpt_is_checked_not_rejected_by_byte_count(self):
        item={"key":"clip_0","url":"https://www.pexels.com/download/video/6435393/",
              "source_page":"https://www.pexels.com/video/a-motorcyclist-putting-on-gloves-6435393/",
              "license":"Pexels License","author":"Andrew Kota","duration":8}
        def fake_ffmpeg(cmd,**kwargs):
            Path(cmd[-1]).write_bytes(b"x"*170_000)
            return SimpleNamespace(returncode=0,stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            dst=Path(tmp)/"moving.mp4"
            with patch.object(r.subprocess,"run",side_effect=fake_ffmpeg), \
                 patch.object(r,"probe",return_value=(7.75,[{"codec_type":"video"}])), \
                 patch.object(r,"motion_verified",return_value=True) as movement:
                r.stream_pexels_excerpt(item,dst,7.75)
                movement.assert_called_once_with(dst)
            with patch.object(r.subprocess,"run",side_effect=fake_ffmpeg), \
                 patch.object(r,"probe",return_value=(7.75,[{"codec_type":"video"}])), \
                 patch.object(r,"motion_verified",return_value=False):
                with self.assertRaisesRegex(RuntimeError,"VISUAL_FROZEN_SEGMENT"):
                    r.stream_pexels_excerpt(item,dst,7.75)

    def test_source_length_is_bounded_to_shot_requirements(self):
        catalog=json.loads((Path(__file__).parent/"episodes.json").read_text(encoding="utf8"))
        e=next(x for x in catalog["episodes"] if x["id"]=="moto-forest-4bd53e13fec4")
        needed=r.required_source_seconds(e,"clip_0")
        self.assertTrue(13<=needed<15)
        self.assertLess(needed,float(e["footage"][0]["duration"]))

    def test_safe_quiet_music_preserves_speech(self):
        for gain in (0.06, 0.08, 0.10, 0.12, 0.18, 0.34):
            self.assertAlmostEqual(r.validated_music_gain(gain), gain)
        for bad in (0, -0.1, 0.35, 1.0, float("nan")):
            with self.assertRaisesRegex(ValueError, "Unsafe music level"):
                r.validated_music_gain(bad)

    def test_voiceover_text_guard(self):
        with patch.object(t, "safe_download") as download:
            with self.assertRaises(ValueError):
                t.render("Коротко", Path("/fake.wav"), Path("/fake"))
            download.assert_not_called()
        self.assertEqual(len(t.MODEL_SHA256), 64)


if __name__ == "__main__":
    unittest.main()
