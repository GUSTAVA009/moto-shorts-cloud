"""Offline original motorcycle research discovery tests."""
import unittest
import source_watch as sw


class StorySourceTests(unittest.TestCase):
    def test_parse_rss_and_dedupe(self):
        xml = "<rss><channel><item><title>Motorcycle restores a vintage bike</title><link>https://www.rideapart.com/news/test-bike/</link></item></channel></rss>"
        rows = sw.parse_rss(xml)
        self.assertEqual(len(rows), 1)
        ideas = sw.new_ideas([], rows)
        self.assertEqual(ideas[0]["topic"], "tech")
        self.assertEqual(sw.new_ideas([ideas[0]["id"]], rows), [])

    def test_untrusted_feed_or_non_https_excluded(self):
        self.assertIsNone(sw.make_candidate("Breaking", "http://www.rideapart.com/news/b"))
        self.assertIsNone(sw.make_candidate("Breaking", "https://bad-site.example/news"))

    def test_science_and_nature_included_as_research_only(self):
        data = [
            ("A colorful octopus changes its skin", "https://www.sciencedaily.com/releases/2026/10/octopus.htm", "nature"),
            ("Nasa mission sees an asteroid", "https://www.jpl.nasa.gov/news/asteroid-story", "space"),
        ]
        out = sw.new_ideas([], data)
        self.assertEqual([x["pillar"] for x in out], ["nature", "space"])
        self.assertTrue(all(x["auto_publish"] is False for x in out))

    def test_avoid_medical_breaking_news_and_politics(self):
        self.assertIsNone(sw.make_candidate(
            "Cancer trial breakthrough", "https://www.sciencedaily.com/releases/2026/10/a.htm", "science"))
        self.assertIsNone(sw.make_candidate(
            "New election results", "https://www.sciencedaily.com/releases/2026/10/b.htm", "history"))

    def test_fair_diverse_leads(self):
        rows = [
            ("A", "https://www.sciencedaily.com/a1", "science"),
            ("B", "https://www.sciencedaily.com/a2", "science"),
            ("C", "https://www.jpl.nasa.gov/news/a3", "space"),
            ("D", "https://www.sciencedaily.com/a4", "nature"),
        ]
        self.assertEqual([x["pillar"] for x in sw.new_ideas([], rows, per_pillar=1)],
                         ["science", "space", "nature"])
        groups = [
            ("science", [("Science A", "https://www.sciencedaily.com/a"), ("Science B", "https://www.sciencedaily.com/b")]),
            ("nature", [("Nature A", "https://www.sciencedaily.com/c")]),
        ]
        self.assertEqual([row[2] for row in sw.round_robin_groups(groups)],
                         ["science", "nature", "science"])

    def test_research_cannot_be_uploaded_without_rights(self):
        x = sw.make_candidate("Latest touring motorcycles", "https://thethrottlehand.com/new-model")
        self.assertEqual(x["status"], "RESEARCH_ONLY_NOT_APPROVED_FOR_PUBLICATION")
        self.assertFalse(x["use_headline_as_narration"])
        self.assertFalse(x["use_source_images_without_license"])


if __name__ == "__main__":
    unittest.main()
