"""Offline copyright, source-ID and redirected-URL regression tests."""
import copy
import unittest

import moto_assets as assets


COMMONS = {
    "source_page": "https://commons.wikimedia.org/wiki/File:Motorsports.webm",
    "url": "https://upload.wikimedia.org/wikipedia/commons/8/85/Motorsports.webm",
    "license": "CC0 1.0", "author": "A. Author",
    "commons_sha1": "ab" * 20, "file_size": 10_000_000,
}
PEXELS = {"source_page": "https://www.pexels.com/video/real-motorcycle-123456/",
          "url": "https://www.pexels.com/download/video/123456/",
          "author": "Movie Maker", "license": "Pexels License"}


class MediaLicenseTests(unittest.TestCase):
    def test_existing_real_pexels_metadata_allowed(self):
        self.assertEqual(assets.validated_media(PEXELS), "123456")

    def test_commons_cc0_is_content_addressed(self):
        self.assertEqual(assets.validated_media(COMMONS), "commons-" + "ab" * 20)

    def test_no_cc_by_sa_or_undefined_public_domain_without_attribution(self):
        for license in ("CC BY 4.0", "CC BY-SA 4.0", "Public domain", None):
            with self.subTest(license=license):
                item = dict(COMMONS, license=license)
                with self.assertRaises(ValueError):
                    assets.validated_media(item)

    def test_no_fake_common_hosts_or_sha(self):
        for change in ({"url": "https://evil.example.com/Motorsports.webm"},
                       {"source_page": "https://fake.wikimedia.org/wiki/File:Motorsports.webm"},
                       {"commons_sha1": "0000"},
                       {"file_size": 0}):
            item = dict(COMMONS, **change)
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    assets.validated_media(item)

    def test_stale_license_or_binary_blocks_render(self):
        data = {"mime": "video/webm", "sha1": COMMONS["commons_sha1"],
                "size": COMMONS["file_size"], "url": COMMONS["url"],
                "extmetadata": {
                    "LicenseShortName": {"value": "CC0"},
                    "LicenseUrl": {"value": "https://creativecommons.org/publicdomain/zero/1.0/deed.en"},
                }}
        self.assertEqual(
            assets.verified_commons(COMMONS, fetch=lambda _: ("File:Motorsports.webm", data)),
            "commons-" + "ab" * 20,
        )
        data["sha1"] = "00" * 20
        with self.assertRaisesRegex(ValueError, "content changed"):
            assets.verified_commons(COMMONS, fetch=lambda _: ("File:Motorsports.webm", data))

    def test_build_candidate_only_with_full_verified_license(self):
        info = {"mime": "video/webm", "sha1": "cd" * 20,
                "size": 1_000_000,
                "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Motorcycle.webm",
                "extmetadata": {
                    "LicenseShortName": {"value": "CC0"},
                    "LicenseUrl": {"value": "https://creativecommons.org/publicdomain/zero/1.0/"},
                    "Artist": {"value": "<a>Original creator</a>"}
                }}
        new = assets.build_commons_candidate("File:Motorcycle.webm", info)
        self.assertEqual(new["commons_sha1"], "cd" * 20)
        self.assertEqual(new["author"], "Original creator")
        self.assertEqual(new["license"], "CC0 1.0")
        info["extmetadata"]["LicenseShortName"]["value"] = "CC BY 4.0"
        self.assertIsNone(assets.build_commons_candidate("File:Motorcycle.webm", info))


if __name__ == "__main__":
    unittest.main()
