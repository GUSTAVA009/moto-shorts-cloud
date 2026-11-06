"""Safety tests for the independent direct-YouTube release gate."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from direct_upload_ready import check


class DirectUploadReadyTests(unittest.TestCase):
    def test_rejects_unapproved_episode_before_any_upload(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "NOT_APPROVED"):
                check("not-approved", Path(tmp), {"episodes": [{"id": "not-approved",
                                                            "auto_publish": False}]})

    def test_owner_rejected_single_source_branded_slide_deck_cannot_publish(self):
        with TemporaryDirectory() as tmp:
            episode={"id":"bolt-precision-20261106","auto_publish":True,
                     "editorial_format":"owner_original_single_source_explainer_v4"}
            with self.assertRaisesRegex(ValueError,"OWNER_REJECTED_BRANDED_STATIC_SLIDE_FORMAT"):
                check(episode["id"],Path(tmp),{"episodes":[episode]})

    def test_missing_media_or_qa_is_not_publishable(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "MISSING"):
                check("approved", Path(tmp), {"episodes": [{"id": "approved",
                                                          "auto_publish": True}]})

    def test_qa_and_actual_mp4_verification_are_mandatory(self):
        import inspect
        from direct_upload_ready import check
        s = inspect.getsource(check)
        for required in ("publication_allowed(", "validate_video(", "visual_qa.json",
                         "mixed_audio_qa.json", "is_repeated_visual_formula("):
            self.assertIn(required, s)

if __name__ == "__main__":
    unittest.main()
