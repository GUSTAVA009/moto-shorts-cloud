"""Offline checks for legal, durable CC0 source discovery; no web requests."""
import base64
import json
import unittest
import urllib.error

import cc0_source_pool as stock


def media(hex_digit="a"):
    identity = hex_digit * 40
    return {
        "key": "commons_" + identity[:14],
        "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Motorcycle_racing_" + hex_digit + ".webm",
        "source_page": "https://commons.wikimedia.org/wiki/File:Motorcycle_racing_" + hex_digit + ".webm",
        "author": "Original CC0 Camera " + hex_digit,
        "license": "CC0 1.0",
        "commons_sha1": identity,
        "file_size": 2_400_000,
        "source_title": "Motorcycle racing " + hex_digit,
    }


def wrap(data, sha="github-blob-sha"):
    return {
        "sha": sha,
        "content": base64.b64encode(json.dumps(data).encode("utf8")).decode("ascii"),
    }


class CommonsCacheTests(unittest.TestCase):
    def test_duplicate_source_does_not_add_or_waste_another_slot(self):
        first = media("a")
        second = media("b")
        base = {"version":1,"sources":[first]}
        merged, n = stock.append_new(base,[first,second,second])
        self.assertEqual(n, 1)
        self.assertEqual(len(merged["sources"]), 2)
        self.assertEqual(merged["sources"][0], first)
        self.assertEqual(merged["sources"][1], second)
        self.assertEqual(len(base["sources"]), 1)

    def test_only_content_addressed_commercial_cc0_is_persisted(self):
        base = {"version":1,"sources":[]}
        for bad in (
            dict(media(), license="CC BY 4.0"),
            dict(media(), commons_sha1="broken"),
            dict(media(), url="https://random-cdn.example/video.webm"),
        ):
            with self.assertRaises((ValueError, TypeError)):
                stock.append_new(base, [bad])
        with self.assertRaisesRegex(RuntimeError,
                                    "CC0_SOURCE_LEDGER_LICENSE_UNVERIFIED"):
            stock.decode(wrap({"version":1,"sources":[dict(media(),license="CC BY")]}))
        with self.assertRaisesRegex(RuntimeError,"DUPLICATE_ID"):
            stock.decode(wrap({"version":1,"sources":[media(),media()]}))
        self.assertEqual(stock.decode(None), base)

    def test_one_successful_commons_source_is_preserved_for_next_cron(self):
        saved = {}
        calls = []
        def github(method, path, payload=None):
            calls.append((method,path))
            self.assertIn("render-ledger", path) if method=="GET" else self.assertEqual(payload["branch"],"render-ledger")
            if method=="GET":
                if not saved:
                    raise urllib.error.HTTPError(path,404,"missing",{},None)
                return wrap(saved["data"], saved["sha"])
            self.assertEqual(method,"PUT")
            self.assertIn("Accumulate 1",payload["message"])
            saved["data"]=json.loads(base64.b64decode(payload["content"]))
            saved["sha"]="saved-after-commit"
            return {"commit":{"sha":"complete"}}
        a=media("a")
        self.assertEqual(stock.discover(("racing",),github,lambda _: [a]),[a])
        self.assertEqual([x[0] for x in calls],["GET","PUT"])
        calls.clear()
        self.assertEqual(stock.discover(("racing",),github,lambda _: [a]),[a])
        self.assertEqual([x[0] for x in calls],["GET"])
        self.assertEqual(saved["data"]["sources"],[a])

    def test_throttle_keeps_last_verified_cc0_instead_of_clearing_cache(self):
        a=media("a")
        writes=[]
        def github(method,path,payload=None):
            if method=="PUT":
                writes.append(payload)
                return {}
            return wrap({"version":1,"sources":[a]})
        def throttled(theme):
            raise urllib.error.HTTPError("https://commons.wikimedia.org/w/api.php",
                                         429,"too many requests",{},None)
        self.assertEqual(stock.discover(("racing",),github,throttled),[a])
        self.assertEqual(writes,[])
        def missing(method,path,payload=None):
            raise urllib.error.HTTPError(path,404,"missing",{},None)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            stock.discover(("racing",),missing,throttled)
        self.assertEqual(caught.exception.code,429)

    def test_malformed_cached_ledger_never_fakes_videos_or_rewrites(self):
        def wrong(method,path,payload=None):
            if method=="GET":
                return wrap({"version":12,"sources":[]})
            raise AssertionError("Corrupt stock must never be rewritten")
        with self.assertRaisesRegex(RuntimeError,"VERSION_UNSUPPORTED"):
            stock.discover(("racing",),wrong,lambda _: [media()])

if __name__ == "__main__":
    unittest.main()
