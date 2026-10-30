"""No false '10 videos ready' when only scripts exist."""
import hashlib
import unittest
from production_readiness import inventory, production_unavailable


def episode(slug="test-city-001", have_audio=False, preview=True):
    narration = "На мотоцикле у городского перекрёстка водитель проверяет тормоз."
    result = {
        "id": slug, "auto_preview": preview,
        "voice_engine": "aidocmaker_deep", "narration": narration,
    }
    if have_audio:
        result["deep_audio"] = {
            "provider": "aidocmaker.com",
            "voice_id": "deep",
            "transcript_sha256": hashlib.sha256(narration.encode("utf8")).hexdigest(),
            "source_audio_sha256": "1" * 64,
            "preview_url": (
                "https://storage.googleapis.com/"
                "adm--audio-playback--7d--public/mcp-preview/"
                "123e4567-e89b-12d3-a456-426614174000.mp3"
            ),
        }
    return result


class ProductionReadinessTests(unittest.TestCase):
    def test_script_only_reserve_is_not_real_production_stock(self):
        catalog = {"episodes": [episode(), episode("test-other-001")]}
        status = inventory(catalog, set())
        self.assertEqual(status["unrendered_script_drafts"], 2)
        self.assertEqual(status["unrendered_verified_deep_originals"], 0)
        self.assertEqual(status["unrendered_missing_original_deep"], 2)
        self.assertTrue(production_unavailable(status))
        self.assertFalse(status["has_autonomous_deep_tts"])

    def test_real_approved_audio_counts_only_before_render_receipt(self):
        ep = episode(have_audio=True)
        cat = {"episodes": [ep]}
        self.assertEqual(inventory(cat, set())["unrendered_verified_deep_originals"], 1)
        self.assertEqual(inventory(cat, {ep["id"]})["unrendered_verified_deep_originals"], 0)

    def test_rejected_scenic_montage_cannot_enter_production(self):
        ep = episode(have_audio=True)
        ep.update(editorial_rejected=True, auto_preview=True)
        state = inventory({"episodes": [ep]}, set())
        self.assertEqual(state["unrendered_verified_deep_originals"], 0)
        self.assertEqual(state["rejected_visuals"], 1)

    def test_old_or_wrong_voice_cannot_be_counted(self):
        ep = episode(have_audio=True)
        ep["deep_audio"]["voice_id"] = "silero"
        state = inventory({"episodes": [ep]}, set())
        self.assertEqual(state["unrendered_verified_deep_originals"], 0)

    def test_real_catalog_never_claims_full_unattended_tts(self):
        from pathlib import Path
        import json
        cat = json.loads((Path(__file__).parent / "episodes.json").read_text("utf8"))
        state = inventory(cat, {ep["id"] for ep in cat["episodes"]
                                if ep.get("deep_audio") is not None})
        self.assertFalse(state["has_autonomous_deep_tts"])


if __name__ == "__main__":
    unittest.main()
