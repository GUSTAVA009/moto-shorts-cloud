"""Real stock can support several unique source-grounded hooks, not 1 repeated title."""
import json
from pathlib import Path
import unittest
from source_story import compose, require_filmable, scene_for

ROOT=Path(__file__).resolve().parent


class SourceAnchoredUniqueTitleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src=json.loads((ROOT/"verified_pexels_pool.json").read_text("utf8"))["sources"]
        m={s["key"]:s for s in src}
        cls.pair=[m["px_9143349"],m["px_9607291"]]
        assert scene_for(cls.pair[0])[0]=="ride"
        assert scene_for(cls.pair[1])[0]=="stunt"

    def test_seven_distinct_fact_grounded_hooks_for_two_real_actions(self):
        seen=[]
        for _ in range(7):
            draft=compose(self.pair,seen)
            self.assertLessEqual(len(draft["title"]),100)
            self.assertNotIn(draft["title"],seen)
            self.assertEqual(set(require_filmable(draft,self.pair)),{"ride","stunt"})
            self.assertIn("независим",draft["description"].casefold())
            seen.append(draft["title"])
        self.assertEqual(len(set(seen)),7)
        # Extended titles must remain distinct after the former seven-title cap.
        for _ in range(8):
            draft=compose(self.pair,seen)
            self.assertNotIn(draft["title"],seen)
            seen.append(draft["title"])
        self.assertEqual(len(set(seen)),15)

    def test_exhausted_old_narrations_get_a_truly_new_filmable_line(self):
        prior_titles=[]
        prior_narrations=[]
        for _ in range(18):
            draft=compose(self.pair,prior_titles,
                          previous_narrations=prior_narrations)
            self.assertNotIn(draft["narration"],prior_narrations)
            self.assertEqual(set(require_filmable(draft,self.pair)),{"ride","stunt"})
            prior_titles.append(draft["title"])
            prior_narrations.append(draft["narration"])

    def test_owner_originals_prefer_two_visible_moving_motorcycles(self):
        from source_story import select_pair
        all_episodes=json.loads((ROOT/"episodes.json").read_text("utf8"))["episodes"]
        originals=[f for episode in all_episodes for f in episode.get("footage",())
                   if f.get("license")=="LTX OpenRAIL-M"]
        isolated=next(f for f in originals if f.get("scene_action")=="wheel")
        riding=next(f for f in originals if f.get("scene_action")=="riding")
        forest=next(f for f in originals if f.get("scene_action")=="forest")
        selected=select_pair([isolated,riding,forest],used_ids=())
        self.assertEqual([f["scene_action"] for f in selected],["riding","forest"])
        self.assertNotIn(isolated,selected)

    def test_variations_do_not_hide_wrong_source_or_repetitions(self):
        initial=compose(self.pair,[])
        self.assertTrue(initial["title"])
        invalid=[self.pair[0],dict(self.pair[0])]
        with self.assertRaises(ValueError):
            compose(invalid,[])
        # Title diversity is not permission to reuse the same source identity:
        # selection / final visual novelty and license gates stay independent.

if __name__=="__main__":
    unittest.main()
