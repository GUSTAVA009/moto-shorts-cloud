"""Regression: private verified DEEP rendering replenishes automatically.

Only source-audio-backed scripts without a permanent render reservation can
create another private preview; Buffer publication never follows from this.
"""
import unittest
from unittest.mock import patch

from preview_batch_supply import pending_verified_previews


class DeepReserveRefillTests(unittest.TestCase):
    def make(self, id, verified=True, preview=True, rejected=False):
        return {"id":id, "auto_preview":preview, "auto_publish":False,
                "editorial_rejected":rejected,
                "voice_engine":"aidocmaker_deep",
                "voice_profile":"gustava_create_audio_deep_v1",
                "deep_audio":{"voice_id":"deep"} if verified else None}

    def test_text_only_drafts_not_counted_as_renderable(self):
        data={"episodes":[self.make("good"),self.make("text-only",False),
                          self.make("bad-look",True,True,True)]}
        with patch("deep_voice.ready", side_effect=lambda ep:bool(ep.get("deep_audio"))):
            self.assertEqual(pending_verified_previews(data,()),["good"])

    def test_reservation_and_published_posts_never_rerender(self):
        data={"episodes":[self.make("done"),self.make("new")]}
        with patch("deep_voice.ready", side_effect=lambda ep:bool(ep.get("deep_audio"))):
            self.assertEqual(pending_verified_previews(data,{"done"}),["new"])
            self.assertEqual(pending_verified_previews(data,{"done","new"}),[])

    def test_only_unreviewed_private_previews_can_be_selected(self):
        data={"episodes":[self.make("a"),self.make("b",preview=False)]}
        with patch("deep_voice.ready", side_effect=lambda ep:bool(ep.get("deep_audio"))):
            self.assertEqual(pending_verified_previews(data,()),["a"])

    def test_action_finishes_with_real_nonrecursive_dispatch_gate(self):
        from pathlib import Path
        workflow=(Path(__file__).resolve().parent.parent /
                  ".github/workflows/daily-preview.yml").read_text("utf8")
        self.assertIn("NEXT_ORIGINAL_DEEP_RENDER_DISPATCHED",workflow)
        self.assertIn("from preview_batch_supply import pending_verified_previews",workflow)
        self.assertIn("if pending:",workflow)
        self.assertIn("DEEP_RENDER_RESERVE_EXHAUSTED",workflow)
        self.assertIn("github(\"POST\",\"actions/workflows/daily-preview.yml/dispatches\"",workflow)


if __name__ == "__main__":
    unittest.main()
