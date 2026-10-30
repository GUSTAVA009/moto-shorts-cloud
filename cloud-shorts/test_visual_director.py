"""Regression for the specific unrelated-helmet and A/B/A/B Shorts failures."""
import unittest
from visual_director import verify_story_subject, directed_plan, MIN_SCENE_SECONDS

def video(key,name,duration=20):
    return {"key":key,"source_page":"https://www.pexels.com/video/"+name+"-123456/",
            "source_title":name.replace("-"," "),"duration":duration,
            "topics":["helmet","city"]}

def ep(footage,title="Что важнее при выборе мотошлема?"):
    return {"id":"moto-test","title":title,"narration":"Проверь шлем, ремешок и обзор.",
            "footage":footage,"shots":[
                {"source":"a","start":0.,"seconds":2.15},
                {"source":"b","start":0.,"seconds":2.15},
                {"source":"a","start":2.15,"seconds":2.15},
                {"source":"b","start":2.15,"seconds":2.15},
            ]}

class VisualDirectionTests(unittest.TestCase):
    def test_actual_failed_helmet_stock_rejected_even_if_tag_says_helmet(self):
        f=[video("a","person-riding-his-motorcycle"),
           video("b","close-up-shot-of-a-man-on-a-motorcycle")]
        x=ep(f)
        with self.assertRaisesRegex(ValueError,"VISUAL_TOPIC_MISMATCH"):
            verify_story_subject(x)

    def test_true_helmet_first_and_no_pingpong_for_16_seconds(self):
        f=[video("a","motorcycle-riding-forest"),
           video("b","man-putting-on-motorcycle-helmet",24)]
        x=ep(f)
        self.assertEqual(verify_story_subject(x)["evidence_sources"],["b"])
        seq=directed_plan(x,{"a":20,"b":24},16.55)
        self.assertEqual([s["source"] for s in seq],["b","a"])
        self.assertTrue(all(s["seconds"]>=MIN_SCENE_SECONDS for s in seq))
        self.assertAlmostEqual(sum(s["seconds"] for s in seq),16.55,places=2)

    def test_three_actual_distinct_chapters_not_12_flash_cuts(self):
        f=[video("a","motorcycle-riding-forest"),video("b","motorcycle-mountain-pass"),
           video("c","motorcycle-riding-on-road")]
        x=ep(f,title="Горный маршрут на мотоцикле")
        x["shots"].append({"source":"c","start":0,"seconds":2.15})
        seq=directed_plan(x,{"a":20,"b":20,"c":20},18)
        self.assertEqual(len(seq),3)
        self.assertEqual([s["source"] for s in seq],["a","b","c"])
        self.assertTrue(all(5<=s["seconds"]<=7 for s in seq))

    def test_title_relevant_source_not_possible_when_clip_too_short(self):
        f=[video("a","man-with-motorcycle-helmet",9),video("b","motorcycle-street",9)]
        x=ep(f)
        with self.assertRaisesRegex(RuntimeError,"VISUAL_DURATION_SHORTAGE"):
            directed_plan(x,{"a":9,"b":9},21)

    def test_publisher_visual_proof_prevents_faked_scenes(self):
        import tempfile, json
        from pathlib import Path
        from visual_director import verified_visual_artifact
        f=[video("a","man-putting-on-motorcycle-helmet",20),
           video("b","motorcycle-riding-city",20)]
        x=ep(f)
        x["visual_director_version"]=2
        with tempfile.TemporaryDirectory() as td:
            mp4=Path(td)/"result.mp4"
            with self.assertRaisesRegex(ValueError,"VISUAL_QA_MISSING"):
                verified_visual_artifact(x,mp4)
            good=directed_plan(x,{"a":20,"b":20},16)
            proof={"version":2,"passed":True,"episode":x["id"],
                   "subject":"helmet","sequence":good,
                   "source_sequence":[p["source"] for p in good],
                   "source_reused_in_short":False}
            (Path(td)/"visual_qa.json").write_text(json.dumps(proof),encoding="utf8")
            self.assertTrue(verified_visual_artifact(x,mp4)["passed"])
            proof["source_sequence"]=["a","b","a"]
            (Path(td)/"visual_qa.json").write_text(json.dumps(proof),encoding="utf8")
            with self.assertRaisesRegex(ValueError,"VISUAL_QA_REJECTED"):
                verified_visual_artifact(x,mp4)


    def test_real_user_rejected_screenshot_fails_claim_coverage(self):
        x={
            "id":"moto-helmet-fit-deep-20261030",
            "auto_preview":True,"auto_publish":False,
            "visual_director_version":3,
            "title":"МОТОШЛЕМ: 3 проверки перед выездом",
            "narration":("Посмотри на шлем. Он должен плотно сидеть и не мешать обзору. "
                         "Перед поездкой проверь размер и застегни ремешок."),
            "footage":[
                video("a","close-up-shot-of-a-man-wearing-goggles-and-helmet"),
                video("b","man-wearing-a-helmet"),
                video("c","man-riding-a-motorcycle-with-helmet")],
            "shots":[{"source":"a","start":0,"seconds":7.6},
                     {"source":"b","start":0,"seconds":4.2},
                     {"source":"c","start":0,"seconds":11.5}],
        }
        from visual_director import verify_story_subject
        with self.assertRaisesRegex(ValueError,"VISUAL_ACTION_STORYBOARD_MISSING"):
            verify_story_subject(x)
        x["visual_beats"]=[
            {"action":"helmet_fit","source":"b"},
            {"action":"helmet_view","source":"a"},
            {"action":"helmet_strap","source":"c"}]
        with self.assertRaisesRegex(ValueError,"VISUAL_ACTION_MISMATCH"):
            verify_story_subject(x)

    def test_v3_passive_helmet_closeup_cannot_fill_seven_seconds(self):
        from visual_director import scene_duration_limit
        e={"visual_director_version":3}
        self.assertLessEqual(scene_duration_limit(
            e,video("a","close-up-shot-of-a-man-wearing-helmet")),3.5)
        self.assertGreater(scene_duration_limit(
            e,video("b","biker-riding-motorcycle")),3.3)

    def test_guide_requires_real_visual_approval_for_auto_publish(self):
        from visual_director import verify_action_storyboard
        x={"id":"moto-helmet-new","auto_publish":True,
           "visual_director_version":3,
           "title":"Мотошлем: проверь посадку и ремешок",
           "narration":"Проверь посадку шлема, затем застегни ремешок.",
           "footage":[video("fit","person-adjusting-motorcycle-helmet"),
                      video("strap","rider-fastening-helmet-chin-strap")],
           "shots":[{"source":"fit","start":0,"seconds":4},
                    {"source":"strap","start":0,"seconds":4}],
           "visual_beats":[{"action":"helmet_fit","source":"fit"},
                           {"action":"helmet_strap","source":"strap"}]}
        with self.assertRaisesRegex(ValueError,"VISUAL_REVIEW_REQUIRED"):
            verify_action_storyboard(x)
        from visual_director import visual_asset_fingerprint
        x["visual_review"]={
            "status":"human_approved",
            "asset_fingerprint":visual_asset_fingerprint(x)}
        self.assertEqual(verify_action_storyboard(x),["helmet_fit","helmet_strap"])
        x["shots"][0]["start"]=1.0
        with self.assertRaisesRegex(ValueError,"VISUAL_REVIEW_REQUIRED"):
            verify_action_storyboard(x)


    def test_three_story_chapters_verified_against_page_slugs(self):
        from visual_director import verify_scene_script_anchors
        ep={
            "title":"Три момента мотоциклиста",
            "narration":"Закрываешь визор. На дороге забываешь обо всём. После поездки снимаешь шлем.",
            "footage":[video("a","woman-closing-the-visor-of-her-helmet"),
                       video("b","man-wearing-a-helmet-while-traveling-on-a-motorbike"),
                       video("c","man-removing-his-helmet-and-smiling")],
            "scene_script_anchors":[
                {"source":"a","action":"visor_close","spoken_anchor":"Закрываешь визор"},
                {"source":"b","action":"riding","spoken_anchor":"На дороге"},
                {"source":"c","action":"helmet_removal","spoken_anchor":"После поездки снимаешь шлем"},
            ],
        }
        self.assertEqual(verify_scene_script_anchors(ep),["a","b","c"])
        ep["scene_script_anchors"][1]["source"]="c"
        with self.assertRaisesRegex(ValueError,"VISUAL_BEATS_OFF_SCRIPT"):
            verify_scene_script_anchors(ep)

    def test_object_mismatch_on_other_safety_guides(self):
        f=[video("a","road-motorcycle"),video("b","riding-in-town")]
        x=ep(f,title="Как проверить тормоза?")
        with self.assertRaisesRegex(ValueError,"VISUAL_TOPIC_MISMATCH"):
            verify_story_subject(x)

if __name__=="__main__":
    unittest.main()
