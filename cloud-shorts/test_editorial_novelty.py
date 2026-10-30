"""Proof that distinct Pexels IDs alone do NOT make an old scenic formula new."""
import json
from pathlib import Path
import unittest
import editorial_novelty as n


def scenic(slug, ids):
    return {
        "id": slug,
        "footage": [
            {"source_page": "https://www.pexels.com/video/mountain-travel-" + str(ids[0]) + "/",
             "source_title": "epic scenic motorcycle mountain road trip"},
            {"source_page": "https://www.pexels.com/video/autumn-riding-" + str(ids[1]) + "/",
             "source_title": "beautiful ride through autumn forest"},
        ],
    }


class EditorialNoveltyTests(unittest.TestCase):
    def test_new_pexels_ids_cannot_repeat_mountain_forest_montage(self):
        past = [scenic("older-mountain", [90000001,90000002]),
                scenic("older-forest", [90000003,90000004])]
        new = scenic("new-but-same-scenes", [99999901,99999902])
        self.assertTrue(n.is_repeated_visual_formula(new, past))
        with self.assertRaisesRegex(ValueError, "REPEATED_SCENIC_MONTAGE"):
            n.require_novel_visual_story(new, past)

    def test_real_mechanical_action_is_not_just_scenery(self):
        actual = {
            "id": "repair-action",
            "footage": [
                {"source_title": "mechanic adjusting motorcycle wheel",
                 "source_page": "https://www.pexels.com/video/mechanic-90000005/"},
                {"source_title": "workshop motorcycle engine assembly",
                 "source_page": "https://www.pexels.com/video/engine-90000006/"},
            ],
        }
        self.assertFalse(n.is_scenic_only_montage(actual))
        n.require_novel_visual_story(actual, [
            scenic("old-a", [90000001,90000002]),
            scenic("old-b", [90000003,90000004]),
        ])

    def test_empty_sources_or_human_written_tags_are_not_scenic_evidence(self):
        only_tags = {"id":"tags", "footage":[{"topics":["mountain","forest"],
                     "source_title":"precision mechanical repair"}]}
        self.assertFalse(n.is_scenic_only_montage(only_tags))

    def test_owner_rejected_preview_always_blocked(self):
        episode = scenic("owner-rejected", [90000001,90000002])
        episode["editorial_rejected"] = True
        with self.assertRaisesRegex(ValueError, "OWNER_REJECTED"):
            n.require_novel_visual_story(episode, [])

    def test_real_mountain_forest_preview_is_rejected_against_history(self):
        catalog = json.loads(
            (Path(__file__).parent / "episodes.json").read_text("utf8")
        )["episodes"]
        actual = next(e for e in catalog
                      if e["id"] == "moto-routes-contrast-deep-20261030")
        self.assertTrue(n.is_scenic_only_montage(actual))
        self.assertTrue(n.is_repeated_visual_formula(actual, catalog))
        self.assertTrue(actual["editorial_rejected"])
        self.assertFalse(actual["auto_publish"])


if __name__ == "__main__":
    unittest.main()
