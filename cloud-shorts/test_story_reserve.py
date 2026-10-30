"""Exhaustive offline proof of 150,000 distinct reserve scripts and headlines."""
import unittest
import story_reserve as r


class ScenarioReserveTests(unittest.TestCase):
    def test_every_address_has_distinct_usable_script_and_headline(self):
        self.assertEqual(r.RESERVE_CAPACITY, 150000)
        titles, narrations, ids = set(), set(), set()
        for index in range(r.RESERVE_CAPACITY):
            item = r.at(index)
            self.assertLessEqual(len(item["title"]), 100)
            self.assertTrue(125 <= len(item["narration"]) <= 300)
            self.assertTrue(item["title"].endswith("#shorts"))
            self.assertTrue(item["description"].rstrip().endswith("#shorts"))
            self.assertTrue(item["narration"].startswith("Мотоцикл"))
            self.assertNotIn("хапыч", item["narration"].casefold())
            self.assertNotIn("эндуро", item["narration"].casefold())
            titles.add(item["title"])
            narrations.add(item["narration"])
            ids.add(item["_reserve_id"])
        self.assertEqual(len(titles), r.RESERVE_CAPACITY)
        self.assertEqual(len(narrations), r.RESERVE_CAPACITY)
        self.assertEqual(len(ids), r.RESERVE_CAPACITY)

    def test_no_wrap_when_theme_is_exhausted(self):
        used = {f"r2-forest-{i:04d}" for i in range(10000)}
        with self.assertRaisesRegex(RuntimeError, "EXHAUSTED"):
            r.choose("forest", [], [], used_ids=used)

    def test_persistent_identity_and_title_guard(self):
        first = r.choose("city", [], [])
        second = r.choose("city", [], [first["title"]],
                          used_ids=[first["_reserve_id"]])
        self.assertNotEqual(first["title"], second["title"])
        self.assertNotEqual(first["_reserve_id"], second["_reserve_id"])

    def test_consumption_counts_valid_unique_ids_only(self):
        self.assertEqual(r.remaining([]), 150000)
        self.assertEqual(r.remaining(["r2-city-0001", "r2-city-0001",
                                      "r2-forest-9999", "bogus", "r2-city-99999"]),
                         149998)

    def test_index_boundaries(self):
        for bad in (-1, 150000, True, 10.5):
            with self.assertRaises(ValueError):
                r.at(bad)
        with self.assertRaises(ValueError):
            r.compose("bad-theme", 0)


if __name__ == "__main__":
    unittest.main()
