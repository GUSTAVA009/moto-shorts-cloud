"""Fail-closed tests: curated Shorts bank stays valid after seeds are consumed."""
from pathlib import Path
import copy
import json
import unittest

import autofill_catalog as af
from editorial_guard import validate_catalog
from render_episode import validate_episode


class CatalogAutofillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        here = Path(__file__).resolve().parent
        cls.catalog = json.loads((here / "episodes.json").read_text(encoding="utf8"))
        cls.bank = json.loads((here / "seed_backlog.json").read_text(encoding="utf8"))
        cls.remaining = [x for x in cls.bank["episodes"]
                         if x["id"] not in {e["id"] for e in cls.catalog["episodes"]}]

    def test_all_original_seeds_validate_individually_and_in_catalog(self):
        catalog = copy.deepcopy(self.catalog)
        existing = {x["id"] for x in catalog["episodes"]}
        for ep in self.bank["episodes"]:
            self.assertTrue(ep.get("auto_preview") is True)
            self.assertTrue(ep.get("auto_publish") is True)
            self.assertEqual(ep.get("voice_engine"), "kokoro_ru_dima")
            self.assertEqual(validate_episode(ep), ep["id"])
            if ep["id"] not in existing:
                catalog["episodes"].append(ep)
                existing.add(ep["id"])
            validate_catalog(catalog)

    def test_do_not_replenish_while_three_unique_episodes_are_waiting(self):
        self.assertIsNone(af.candidate(self.catalog, self.bank, set()))

    def test_replenish_once_when_pending_runs_low(self):
        if not self.remaining:
            self.skipTest("Curated bank exhausted; test availability separately")
        active = {ep["id"] for ep in self.catalog["episodes"]
                  if ep.get("auto_preview") is True}
        selection = af.candidate(self.catalog, self.bank, active)
        self.assertIsNotNone(selection)
        self.assertEqual(selection[1], self.remaining[0]["id"])
        self.assertEqual(len(selection[0]["episodes"]),
                         len(self.catalog["episodes"]) + 1)

    def test_second_run_is_idempotent(self):
        if len(self.remaining) < 2:
            self.skipTest("Only one seed left; next run cannot invent another")
        active = {ep["id"] for ep in self.catalog["episodes"]
                  if ep.get("auto_preview") is True}
        new_catalog, slug = af.candidate(self.catalog, self.bank, active)
        updated = set(active)
        updated.add(slug)
        next_catalog, next_slug = af.candidate(new_catalog, self.bank, updated)
        self.assertEqual(next_slug, self.remaining[1]["id"])
        self.assertNotEqual(slug, next_slug)

    def test_ten_target_still_requests_original_when_two_wait(self):
        self.assertIsNone(af.candidate(self.catalog, self.bank, set()))
        # Existing stock can be exhausted, but a higher rolling target
        # must explicitly report the source requirement.
        with self.assertRaisesRegex(RuntimeError, "EXHAUSTED"):
            af.candidate(self.catalog, self.bank,
                         {e["id"] for e in self.catalog["episodes"] if e.get("auto_preview")},
                         target=10)

    def test_empty_bank_must_not_forge_new_footage(self):
        active = {ep["id"] for ep in self.catalog["episodes"]
                  if ep.get("auto_preview") is True}
        with self.assertRaisesRegex(RuntimeError, "EXHAUSTED"):
            af.candidate(self.catalog, {"version": 1, "episodes": []}, active)


if __name__ == "__main__":
    unittest.main()
