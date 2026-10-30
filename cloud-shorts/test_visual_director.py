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

    def test_object_mismatch_on_other_safety_guides(self):
        f=[video("a","road-motorcycle"),video("b","riding-in-town")]
        x=ep(f,title="Как проверить тормоза?")
        with self.assertRaisesRegex(ValueError,"VISUAL_TOPIC_MISMATCH"):
            verify_story_subject(x)

if __name__=="__main__":
    unittest.main()
