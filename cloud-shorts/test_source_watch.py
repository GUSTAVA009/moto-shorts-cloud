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

    def test_research_cannot_be_uploaded_without_rights(self):
        x = sw.make_candidate("Latest touring motorcycles", "https://thethrottlehand.com/new-model")
        self.assertEqual(x["status"], "RESEARCH_ONLY_NOT_APPROVED_FOR_PUBLICATION")
        self.assertFalse(x["use_headline_as_narration"])
        self.assertFalse(x["use_source_images_without_license"])


if __name__ == "__main__":
    unittest.main()
