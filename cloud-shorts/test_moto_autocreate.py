"""Offline tests of new licensed stock intake and original Russian story creation."""
import copy
import json
from pathlib import Path
import unittest

import moto_autocreate as s


def fixture(id, name, action="motorcycle-ride"):
    return {
        "id": id,
        "url": "https://www.pexels.com/video/" + action + "-" + str(id) + "/",
        "duration": 24, "user": {"name": name},
        "video_files": [{"id": id, "link": "https://videos.pexels.com/media/demo.mp4"}],
    }


def story():
    return {
        "title": "Мотоцикл и новая дорога: на что смотреть? #shorts",
        "narration": ("Мотоцикл открывает совершенно другую дорогу. Один райдер "
                      "выбирает спокойный маршрут, другой любит извилистую тропу. "
                      "Но важнее всего заранее видеть покрытие и помнить об "
                      "окружающих. А какая дорога нравится тебе больше?"),
        "description": "Две самостоятельные мотоистории, новые маршруты и впечатления. #shorts",
        "caption_start": "НОВАЯ ДОРОГА",
        "caption_middle": "ДВЕ РАЗНЫЕ ПОЕЗДКИ",
        "caption_end": "КАКОЙ МАРШРУТ ТВОЙ?",
    }


class NewMotoSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(
            (Path(__file__).resolve().parent / "episodes.json").read_text(encoding="utf8"))

    def test_pexels_official_source_and_two_authors(self):
        data = {"videos": [fixture(90000001, "Alice Rider"),
                           fixture(90000002, "Bob Mechanic"),
                           fixture(90000003, "Bob Mechanic"),
                           fixture(90000004, "Daria Rider")]}
        def fetch(url, headers):
            self.assertIn("api.pexels.com/v1/videos/search", url)
            self.assertEqual(headers["Authorization"], "not-a-real-key")
            return data
        result = s.pexels_results(s.THEMES[0], 1, "not-a-real-key", fetch=fetch)
        self.assertEqual(len(result), 4)
        selected = s.choose_sources(result, set(), n=3)
        self.assertEqual(len(selected), 3)
        self.assertEqual(len({x["author"] for x in selected}), 3)

    def test_non_motorcycle_pexels_video_rejected(self):
        wrong = fixture(90000001, "Alice Rider")
        wrong["url"] = "https://www.pexels.com/video/cute-cat-90000001/"
        data = {"videos": [wrong]}
        self.assertEqual(s.pexels_results(s.THEMES[0], 1, "demo",
                                         fetch=lambda a,b: data), [])

    def test_no_key_no_invented_stock_sources(self):
        self.assertEqual(s.pexels_results(s.THEMES[0], 1, ""), [])
        self.assertEqual(s.choose_sources([], set()), [])

    def test_offline_story_reserve_without_model_credentials(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {"OPENAI_API_KEY": "", "OPENROUTER_API_KEY": ""}):
            a = s.original_story(s.THEMES[0], [], [])
            b = s.original_story(s.THEMES[0], [], [a["title"]])
        self.assertNotEqual(a["title"], b["title"])
        self.assertTrue(125 <= len(a["narration"]) <= 300)
        self.assertTrue(a["narration"].startswith("Мотоцикл"))
        self.assertEqual(a["_generation_source"], "offline_editorial_reserve_v3")

    def test_verified_public_pexels_pool_stays_unique(self):
        bank = json.loads((Path(__file__).resolve().parent / "verified_pexels_pool.json").read_text("utf8"))
        from moto_assets import validated_media, source_id
        sources = bank["sources"]
        self.assertGreaterEqual(len(sources), 20)
        ids = [source_id(x) for x in sources]
        self.assertEqual(len(ids), len(set(ids)))
        for entry in sources:
            self.assertEqual(validated_media(entry), source_id(entry))
        self.assertTrue(s.curated_pexels_results(s.THEMES[0]))
        self.assertFalse(s.curated_pexels_results(s.THEMES[0], set(ids)))

    def test_offline_fallback_when_inference_service_fails(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {"OPENAI_API_KEY": "", "OPENROUTER_API_KEY": ""}):
            result = s.original_story(s.THEMES[0], [], [],
                  client=("https://model.example", "example-token", "test-model"),
                  fetch=lambda *args: (_ for _ in ()).throw(OSError("Provider unavailable")))
        self.assertEqual(result["_generation_source"], "offline_editorial_reserve_v3")

    def test_active_rolling_batch_script_can_be_used_for_new_episode(self):
        from unittest.mock import patch
        import story_reserve
        planned = story_reserve.at(10_000)
        planned["theme"] = "motocross"
        media = s.pexels_results(s.THEMES[1], 1, "demo",
                fetch=lambda a,b: {"videos": [
                    fixture(90000001, "Alice Rider", "motocross-jump"),
                    fixture(90000002, "Bob Mechanic", "motorcycle-wheel-repair"),
                    fixture(90000004, "Daria Rider", "motorcycle-race")]})
        relevant = (dict(self.catalog, episodes=self.catalog["episodes"][:-1])
                    if self.catalog["episodes"][-1]["editorial"]["bike"] == s.THEMES[1][3]
                    else self.catalog)
        with patch.dict("os.environ", {"PEXELS_API_KEY": ""}):
            with patch.object(s, "curated_pexels_results", return_value=media), \
                 patch.object(s, "commons_results", return_value=[]):
                ep = s.create_one(relevant,
                                  source_fetch=lambda *args: [],
                                  commons_fetch=lambda *args: [],
                                  prose_factory=lambda *args: (_ for _ in ()).throw(
                                      AssertionError("Active reserve draft should win")),
                                  prepared_scripts=[planned])
        self.assertEqual(ep["story_reserve_id"], planned["_reserve_id"])
        self.assertNotEqual(ep["narration"], planned["narration"])
        self.assertNotEqual(ep["title"], planned["title"])
        self.assertIn("трамплин", ep["narration"])
        self.assertIn("колес", ep["narration"])
        self.assertFalse(ep["auto_publish"])

    def test_supplier_never_repeats_last_motorcycle_type(self):
        from unittest.mock import patch
        catalog = dict(self.catalog)
        last = dict(catalog["episodes"][-1])
        last["editorial"] = dict(last["editorial"], bike=s.THEMES[1][3])
        catalog["episodes"] = list(catalog["episodes"][:-1]) + [last]
        planned = s.offline_original_story(s.THEMES[1], [], [])
        planned["theme"] = "motocross"
        media = s.pexels_results(s.THEMES[1], 1, "test",
                fetch=lambda a,b: {"videos":[
                    fixture(90000001, "Alice Rider"),
                    fixture(90000002, "Bob Mechanic")]})
        with patch.dict("os.environ", {"PEXELS_API_KEY": ""}):
            with patch.object(s, "curated_pexels_results",
                 side_effect=lambda theme,used: media if theme[0]=="motocross" else []):
                with self.assertRaisesRegex(RuntimeError, "NO_NEW_ACTION_MATCHING_LICENSED_MOTO_CLIPS"):
                    s.create_one(catalog, source_fetch=lambda *a: [],
                                 commons_fetch=lambda *a: [],
                                 prepared_scripts=[planned])

    def test_reject_model_fabricating_numbers(self):
        result = story()
        result["narration"] += " Максимальная скорость 230 километров в час."
        fake = {"choices": [{"message": {"content": json.dumps(result, ensure_ascii=False)}}]}
        with self.assertRaisesRegex(ValueError, "numerical"):
            s.original_story(s.THEMES[0], [], [], client=("https://example.com", "key", "test"),
                             fetch=lambda a,b,c: fake)


    def test_one_keyless_commons_call_per_full_autonomous_research_cycle(self):
        from unittest.mock import patch
        seen = []
        def fetch(theme):
            seen.append(theme[0])
            return []
        with patch.dict("os.environ", {"PEXELS_API_KEY":""}), \
             patch.object(s, "curated_pexels_results", return_value=[]):
            with self.assertRaisesRegex(RuntimeError,
                                       "NO_NEW_ACTION_MATCHING_LICENSED_MOTO_CLIPS"):
                s.create_one(self.catalog, commons_fetch=fetch)
        self.assertEqual(len(seen), 1)
        self.assertIn(seen[0], [theme[0] for theme in s.THEMES])

    def test_cc0_http_429_is_a_one_shot_cycle_blocker_not_fifteen_retries(self):
        from unittest.mock import patch
        import urllib.error
        seen = []
        def throttled(theme):
            seen.append(theme[0])
            raise urllib.error.HTTPError(
                "https://commons.wikimedia.org/w/api.php", 429,
                "Too Many Requests", {}, None)
        with patch.dict("os.environ", {"PEXELS_API_KEY":""}), \
             patch.object(s, "curated_pexels_results", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "COMMONS_RATE_LIMITED"):
                s.create_one(self.catalog, commons_fetch=throttled)
        self.assertEqual(len(seen), 1)

    def test_action_paired_keyless_narration_contains_exact_two_scene_actions(self):
        from source_story import compose, require_filmable, select_pair, scene_for
        shots=[
            {"key":"a", "url":"https://www.pexels.com/download/video/90000001/",
             "source_page":"https://www.pexels.com/video/motocross-jump-90000001/",
             "author":"First Creator", "license":"Pexels License", "duration":14},
            {"key":"b", "url":"https://www.pexels.com/download/video/90000002/",
             "source_page":"https://www.pexels.com/video/motorcycle-wheel-repair-90000002/",
             "author":"Second Creator", "license":"Pexels License", "duration":14},
        ]
        pair=select_pair(shots, set())
        self.assertEqual(len(pair), 2)
        story=compose(pair, [])
        self.assertEqual(story["_generation_source"],"keyless_action_filmable_v1")
        self.assertEqual(require_filmable(story,pair),["jump","wheel"])
        self.assertTrue(125<=len(story["narration"])<=300)
        self.assertIn("трамплин",story["narration"])
        self.assertIn("колес",story["narration"])
        self.assertIsNone(scene_for(dict(shots[0],source_page=
             "https://www.pexels.com/video/motorcycle-portrait-90000001/")))
        with self.assertRaisesRegex(ValueError,"UNRELATED_BORING_SCRIPT"):
            require_filmable({"narration":
                "Мотоцикл красивый, а дорога очень интересная. "
                "У каждого свой выбор. Смотри на дорогу и готовься заранее. "
                "Какой путь выбрал бы ты? Поделись этим роликом с другом."},pair)

    def test_autonomous_source_selection_rejects_generic_reruns_or_same_creator(self):
        from source_story import select_pair, compose
        base = dict(key="a",url="https://www.pexels.com/download/video/90000001/",
                    source_page="https://www.pexels.com/video/motorcycle-ride-90000001/",
                    author="One",license="Pexels License",duration=15)
        second=dict(base,key="b",url="https://www.pexels.com/download/video/90000002/",
                    source_page="https://www.pexels.com/video/motorcycle-ride-90000002/",
                    author="Two")
        self.assertEqual(select_pair([base,second],set()),[])
        with self.assertRaisesRegex(ValueError,"NO_ACTION_DIVERSITY"):
            compose([base,second],[])
        second["source_page"]="https://www.pexels.com/video/motorcycle-wheel-repair-90000002/"
        second["author"]="One"
        self.assertEqual(select_pair([base,second],set()),[])
        second["author"]="Two"
        self.assertEqual(len(select_pair([base,second],set())),2)
        self.assertEqual(select_pair([base,second],{"90000001"}),[])


    def test_reference_style_requires_real_touring_and_racing_scenes(self):
        """Reference is a creative *format*, not its copyrighted media/text."""
        from source_story import scene_for, compose, select_pair, require_filmable
        journey = {
            "key":"j", "url":"https://www.pexels.com/download/video/90000011/",
            "source_page":"https://www.pexels.com/video/motorcycle-touring-journey-90000011/",
            "author":"Touring Camera", "license":"Pexels License", "duration":18}
        race = {
            "key":"r", "url":"https://www.pexels.com/download/video/90000012/",
            "source_page":"https://www.pexels.com/video/motocross-race-on-track-90000012/",
            "author":"Track Camera", "license":"Pexels License", "duration":17}
        bland = {
            "key":"b", "url":"https://www.pexels.com/download/video/90000013/",
            "source_page":"https://www.pexels.com/video/motorcycle-ride-90000013/",
            "author":"Road Camera", "license":"Pexels License", "duration":18}
        self.assertEqual(scene_for(journey)[0],"touring")
        self.assertEqual(scene_for(race)[0],"race")
        pair=select_pair([bland,journey,race],set())
        self.assertEqual([media["key"] for media in pair],["j","r"])
        draft=compose(pair,[])
        self.assertEqual(draft["_creative_treatment"],"myth_vs_reality_irony")
        self.assertEqual(draft["_editorial_format"],"ironic_touring_vs_track_myth")
        self.assertEqual(require_filmable(draft,pair),["touring","race"])
        self.assertTrue(125<=len(draft["narration"])<=300)
        self.assertIn("турист",draft["narration"].lower()) if "турист" in draft["narration"].lower() else self.assertIn("путешеств",draft["narration"].lower())
        # A provider title may say racing, but the frames can show only one rider.
        # The safe generated story mentions the actual track, not competition.
        self.assertIn("трек",draft["narration"].lower())
        self.assertNotIn("мотоциклисты участвуют в гонке",draft["narration"].lower())
        self.assertNotIn("эндуро",draft["narration"].lower())
        self.assertEqual(compose([bland,race],[])["_editorial_format"],
                         "source_anchored_action_contrast")
        with self.assertRaisesRegex(ValueError,"MYTH_TITLE_PREVIOUSLY_USED"):
            compose(pair,[draft["title"]])
        race["author"]=journey["author"]
        self.assertEqual(select_pair([journey,race],set()),[])

    def test_cross_theme_touring_story_is_private_and_keeps_exact_deep(self):
        from unittest.mock import patch
        tour = {
            "key":"j", "url":"https://www.pexels.com/download/video/90000021/",
            "source_page":"https://www.pexels.com/video/motorcycle-touring-journey-90000021/",
            "author":"Touring Creator","license":"Pexels License","duration":17}
        race = {
            "key":"r", "url":"https://www.pexels.com/download/video/90000022/",
            "source_page":"https://www.pexels.com/video/motocross-race-on-track-90000022/",
            "author":"Track Creator","license":"Pexels License","duration":18}
        def cached(theme, used):
            return [tour] if theme[0]=="roadtrip" else [race] if theme[0]=="racing" else []
        with patch.dict("os.environ",{"PEXELS_API_KEY":""}), \
             patch.object(s,"choose_theme",return_value=s.THEMES[8]), \
             patch.object(s,"curated_pexels_results",side_effect=cached):
            ep=s.create_one(self.catalog, commons_fetch=lambda _:[])
        self.assertEqual(ep["editorial_format"],"ironic_touring_vs_track_myth")
        self.assertEqual(ep["creative_treatment"],"myth_vs_reality_irony")
        self.assertEqual(ep["voice_engine"],"gustava_selfhosted_qwen3")
        self.assertTrue(ep["auto_preview"])
        self.assertFalse(ep["auto_publish"])
        self.assertEqual(ep["music_style"],"race-breakbeat")
        self.assertEqual({media["source_page"] for media in ep["footage"]},
                         {tour["source_page"],race["source_page"]})
        self.assertEqual(len(ep["shots"]),2)

    def test_cross_theme_fresh_repair_and_snow_keeps_truthful_qa_gates(self):
        """Each topic contains just one actionable video; two verified
        independent scenes should still create ONE private render candidate.
        Generic repair must never claim a motor/engine rebuild."""
        from unittest.mock import patch
        from source_story import scene_for, require_filmable
        files=[
            {"key":"r","url":"https://www.pexels.com/download/video/90001231/",
             "source_page":"https://www.pexels.com/video/man-repairing-motorcycle-90001231/",
             "author":"First Independent Mechanic","license":"Pexels License",
             "source_title":"man repairing motorcycle","duration":19},
            {"key":"m","url":"https://www.pexels.com/download/video/90001232/",
             "source_page":"https://www.pexels.com/video/motorcycle-riding-in-snow-90001232/",
             "author":"Second Independent Rider","license":"Pexels License",
             "source_title":"motorcycle riding in snow","duration":19},
        ]
        self.assertEqual(scene_for(files[0])[0],"repair")
        self.assertEqual(scene_for(files[1])[0],"snow")
        assert not any(x["source_page"] in
                       {v["source_page"] for ep in self.catalog["episodes"]
                        for v in ep["footage"]} for x in files)
        def curated(theme, used):
            if theme[0]=="repair":
                return [files[0]]
            if theme[0]=="snow":
                return [files[1]]
            return []
        with patch.dict("os.environ",{"PEXELS_API_KEY":"",
                                       "OPENAI_API_KEY":"",
                                       "OPENROUTER_API_KEY":""}), \
             patch.object(s,"curated_pexels_results",side_effect=curated), \
             patch.object(s,"curated_mixkit_results",return_value=[]):
            ep=s.create_one(self.catalog,source_fetch=lambda *a:[],
                            commons_fetch=lambda *a:[],prepared_scripts=[])
        self.assertEqual(len(ep["footage"]),2)
        self.assertEqual(set(require_filmable(ep,ep["footage"])),{"repair","snow"})
        self.assertTrue(ep["auto_preview"])
        self.assertFalse(ep["auto_publish"])
        self.assertEqual(ep["voice_engine"],"gustava_selfhosted_qwen3")
        self.assertEqual(len(set(x["author"] for x in ep["footage"])),2)
        self.assertTrue(all(x["license"]=="Pexels License" for x in ep["footage"]))
        self.assertNotIn("мотором",ep["narration"].casefold())

    def test_cross_theme_never_reuses_ride_only_pair_or_same_creator(self):
        from unittest.mock import patch
        generic={
           "key":"a","url":"https://www.pexels.com/download/video/90001231/",
           "source_page":"https://www.pexels.com/video/motorcycle-ride-90001231/",
           "author":"First","license":"Pexels License","duration":14}
        other=dict(generic,key="b",author="Second",
                   url="https://www.pexels.com/download/video/90001232/",
                   source_page="https://www.pexels.com/video/motorcycle-riding-90001232/")
        def curated(theme,used):
            return ([generic] if theme[0]=="repair" else
                    [other] if theme[0]=="dirt" else [])
        with patch.dict("os.environ",{"PEXELS_API_KEY":""}), \
             patch.object(s,"curated_pexels_results",side_effect=curated), \
             patch.object(s,"curated_mixkit_results",return_value=[]):
            with self.assertRaisesRegex(RuntimeError,"NO_NEW_ACTION_MATCHING_LICENSED_MOTO_CLIPS"):
                s.create_one(self.catalog,commons_fetch=lambda *_:[])

    def test_new_story_pins_owner_cloud_cpu_voice_not_saas(self):
        from unittest.mock import patch
        import selfhosted_voice as cv
        media = s.pexels_results(s.THEMES[0], 1, "demo",
            fetch=lambda a,b: {"videos": [
                fixture(90000001, "Alice Rider"),
                fixture(90000002, "Bob Mechanic"),
                fixture(90000004, "Daria Rider")]})
        env = {"GUSTAVA_TTS_PROVIDER":cv.VOICE_ENGINE}
        with patch.dict("os.environ", env):
            ep = s.assemble_episode(
                self.catalog, s.choose_theme(self.catalog["episodes"]),
                media[:3], story(), len(self.catalog["episodes"]))
        self.assertEqual(ep["voice_engine"], cv.VOICE_ENGINE)
        self.assertEqual(ep["voice_profile"], cv.PROFILE_ID)
        self.assertEqual(ep["selfhosted_voice_id"],cv.VOICE_ID)
        self.assertTrue(ep["auto_preview"])
        self.assertFalse(ep["auto_publish"])
        self.assertNotIn("deep_audio", ep)

    def test_build_vetted_unique_episode(self):
        media = s.pexels_results(s.THEMES[0], 1, "demo",
              fetch=lambda a,b: {"videos": [
                  fixture(90000001, "Alice Rider"), fixture(90000002, "Bob Mechanic"),
                  fixture(90000004, "Daria Rider")]})
        theme = s.choose_theme(self.catalog["episodes"])
        ep = s.assemble_episode(self.catalog, theme, media[:3],
                                story(), len(self.catalog["episodes"]))
        self.assertFalse(ep["auto_publish"])
        self.assertEqual(len(ep["shots"]), len(ep["footage"]))
        self.assertEqual(len({s["source"] for s in ep["shots"]}),len(ep["shots"]))
        self.assertTrue(all(s["seconds"]>=4 for s in ep["shots"]))
        self.assertEqual(len(ep["footage"]), 3)
        self.assertEqual(len(set(x["source_page"] for x in ep["footage"])), 3)
        self.assertTrue(ep["narration"].startswith("Мотоцикл"))


    def test_verified_2026_pexels_stock_mapped_to_distinct_live_action_scenes(self):
        """Actual official pages and video HEAD/ffprobe checked on 2026-11-01.
        These sources add *potential* raw footage, never counted as MP4.
        """
        import json
        from pathlib import Path
        from source_story import scene_for, select_pair
        from moto_assets import source_id, validated_media
        pool=json.loads((Path(__file__).resolve().parent /
                         "verified_pexels_pool.json").read_text(encoding="utf8"))
        checked={int(x["key"].split("_")[1]):x for x in pool["sources"]
                 if x["key"].startswith("curated_")}
        incoming={31894372,32191741,13470940,15540590,36306512,
                  36926096,35963831,40347388,32659157,29465924}
        self.assertTrue(incoming.issubset(checked))
        for i in incoming:
            clip=checked[i]
            self.assertEqual(source_id(clip),str(i))
            self.assertEqual(validated_media(clip),str(i))
            self.assertEqual(clip["license"],"Pexels License")
            self.assertGreaterEqual(clip["duration"],9.0)
            self.assertLess(clip["duration"],90)
            self.assertIsNotNone(scene_for(clip),str(i))
        self.assertEqual(scene_for(checked[36306512])[0],"city")
        self.assertEqual(scene_for(checked[35963831])[0],"city")
        self.assertEqual(scene_for(checked[31894372])[0],"race")
        self.assertEqual(scene_for(checked[13470940])[0],"mountain")
        from source_story import require_filmable, compose
        pair=select_pair([checked[31894372],checked[13470940]],set())
        self.assertEqual(len(pair),2)
        self.assertEqual(len({x["author"] for x in pair}),2)
        draft=compose(pair,[])
        self.assertEqual(set(require_filmable(draft,pair)),{"race","mountain"})
        self.assertNotIn("https://",draft["narration"])


if __name__ == "__main__":
    unittest.main()
