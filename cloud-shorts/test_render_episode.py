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

    def test_unknown_curated_pexels_duration_is_measured_later_not_invented(self):
        episode={"footage":[{"key":"clip_0","source_page":
            "https://www.pexels.com/video/off-road-motorcycle-adventure-in-muddy-terrain-36365086/"}],
            "shots":[{"source":"clip_0","start":0,"seconds":8.0}]}
        self.assertEqual(r.required_source_seconds(episode,"clip_0"),8.7)
        episode["footage"][0]["duration"]=7.0
        self.assertEqual(r.required_source_seconds(episode,"clip_0"),7.0)
        episode["footage"][0]["duration"]=-5
        with self.assertRaisesRegex(ValueError,"INVALID_DECLARED_SOURCE_DURATION"):
            r.required_source_seconds(episode,"clip_0")

    def test_short_pexels_motocross_duration_is_grounded_not_faked(self):
        data=json.loads((Path(__file__).parent/"episodes.json").read_text(encoding="utf8"))
        ep=next(e for e in data["episodes"] if e["id"]=="gustava-20-p02-20261030")
        # The previously private six-second source was now individually
        # inspected in the exact 100%-ASR 11.4s released MP4.
        self.assertTrue(ep["auto_publish"])
        self.assertEqual(ep["reviewed_mp4_sha256"],
                         "68beafcd34710b62bdc82b5e4ad0474e0b445286a1852df553f53e97b740e253")
        self.assertFalse(ep["source_revision_requested"])
        self.assertEqual(ep["footage"][0]["duration"],6)
        self.assertEqual(ep["shots"][0]["seconds"],5.5)
        self.assertEqual(ep["source_revision_reason"],"undersized_source_motion_verified")
        self.assertLessEqual(r.required_source_seconds(ep,"clip_0"),6)
        self.assertGreaterEqual(sum(s["seconds"] for s in ep["shots"]),12)
        self.assertEqual(r.validate_episode(ep),ep["id"])


    def test_middle_caption_is_after_actual_second_scene_not_before_it(self):
        episode={"creative_treatment":"scene_comparison",
                 "align_middle_caption_to_second_scene":True,
                 "opening_trim_seconds":0.1}
        plan=[{"source":"clip_0","seconds":3.82},
              {"source":"clip_1","seconds":7.942}]
        spans=r.caption_schedule(episode,11.633,plan)
        self.assertEqual(spans[1][0],"caption_middle")
        self.assertAlmostEqual(spans[1][1],3.82-0.1+0.12,places=2)
        self.assertGreater(spans[1][1],plan[0]["seconds"]-.1)
        with self.assertRaisesRegex(RuntimeError,"SCENE_CAPTION_REQUIRES_VERIFIED"):
            r.caption_schedule(episode,11.633,None)

    def test_ironic_reveal_caption_follows_real_second_scene_not_fixed_timer(self):
        episode = {
            "id": "private-myth-preview",
            "creative_treatment": "myth_vs_reality_irony",
            "opening_trim_seconds": 0.10,
        }
        scenes = [{"source":"clip_0","seconds":11.45},
                  {"source":"clip_1","seconds":10.70}]
        spans = r.caption_schedule(episode, 21.95, scenes)
        self.assertEqual([x[0] for x in spans],
                         ["caption_start","caption_middle","caption_end"])
        self.assertAlmostEqual(spans[1][1],11.45-0.10+0.12)
        self.assertGreater(spans[1][1],spans[0][2])
        self.assertLess(spans[1][2],spans[2][1])
        self.assertLess(spans[1][2]-spans[1][1],2.5)
        # No regression to legacy 3.9s cue for normal episodes.
        ordinary=r.caption_schedule({"story_steps":[]},21.95)
        self.assertAlmostEqual(ordinary[1][1],3.9)
        self.assertEqual(len(r.caption_schedule({"story_steps":[{"text":"proof"}]},
                                                 21.95)),2)

    def test_ironic_caption_fails_closed_without_correct_two_scene_proof(self):
        ep={"creative_treatment":"myth_vs_reality_irony",
            "opening_trim_seconds":0.1}
        with self.assertRaisesRegex(RuntimeError,
                                    "MYTH_CAPTION_REQUIRES_VERIFIED_TWO_SHOT_PLAN"):
            r.caption_schedule(ep,21.2,None)
        with self.assertRaisesRegex(RuntimeError,
                                    "MYTH_CAPTION_REQUIRES_VERIFIED_TWO_SHOT_PLAN"):
            r.caption_schedule(ep,21.2,[{"seconds":5.0}])
        with self.assertRaisesRegex(RuntimeError,
                                    "MYTH_CAPTION_CUT_OUTSIDE_READABLE_DURATION"):
            r.caption_schedule(ep,21.2,[{"seconds":19},{"seconds":2}])
        with self.assertRaisesRegex(RuntimeError,
                                    "MYTH_CAPTION_TRANSITION_UNVERIFIED"):
            r.caption_schedule(ep,21.2,[{"seconds":"bad"},{"seconds":5}])

    def test_two_line_overlay_text_never_embeds_ffmpeg_newline_glyph(self):
        one={"text":"ПЕРВЫЙ ВЫЕЗД:","line_count":1}
        two={"text":"ПЕРВЫЙ ВЫЕЗД:" + chr(10) + "улыбка или скорость?",
             "line_count":2}
        self.assertEqual(r.caption_text_lines(one),["ПЕРВЫЙ ВЫЕЗД:"])
        self.assertEqual(r.caption_text_lines(two),
                         ["ПЕРВЫЙ ВЫЕЗД:","улыбка или скорость?"])
        self.assertFalse(any(chr(10) in x for x in r.caption_text_lines(two)))
        with self.assertRaisesRegex(ValueError,"CAPTION_LINES_INVALID"):
            r.caption_text_lines({"text":"title" + chr(10),"line_count":2})

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

    def test_real_six_second_clip_from_declared_eight_never_loops_or_fakes_frames(self):
        item={"key":"clip_0","url":"https://www.pexels.com/download/video/32401566/",
              "source_page":"https://www.pexels.com/video/thrilling-dirt-bike-jump-on-outdoor-track-32401566/",
              "license":"Pexels License","author":"Harvey Tan Villarino","duration":8}
        def ffmpeg_stub(cmd,**kwargs):
            Path(cmd[-1]).write_bytes(b"g"*500_000)
            return SimpleNamespace(returncode=0,stderr="")
        with tempfile.TemporaryDirectory() as td:
            dst=Path(td)/"real-six.mp4"
            with patch.object(r.subprocess,"run",side_effect=ffmpeg_stub) as ffmpeg, \
                 patch.object(r,"probe",return_value=(6.0,[{"codec_type":"video"}])), \
                 patch.object(r,"motion_verified",return_value=True) as motion:
                r.stream_pexels_excerpt(item,dst,8.0)
            self.assertTrue(dst.exists())
            self.assertEqual(ffmpeg.call_count,1)
            self.assertIn("-t",ffmpeg.call_args.args[0])
            self.assertNotIn("-stream_loop",ffmpeg.call_args.args[0])
            motion.assert_called_once_with(dst)
            with patch.object(r.subprocess,"run",side_effect=ffmpeg_stub), \
                 patch.object(r,"probe",return_value=(6.0,[{"codec_type":"video"}])), \
                 patch.object(r,"motion_verified",return_value=False):
                with self.assertRaisesRegex(RuntimeError,"VISUAL_FROZEN_SEGMENT"):
                    r.stream_pexels_excerpt(item,dst,8.0)
            with patch.object(r.subprocess,"run",side_effect=ffmpeg_stub), \
                 patch.object(r,"probe",return_value=(4.0,[{"codec_type":"video"}])):
                with self.assertRaisesRegex(RuntimeError,"missing required scene time"):
                    r.stream_pexels_excerpt(item,dst,8.0)

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
