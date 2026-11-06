"""Regression tests for Github API oversized catalog no-empty-data fallback."""
import base64
import hashlib
import json
import unittest
from github_catalog import decode_catalog


def fixture(obj):
    raw=json.dumps(obj).encode("utf8")
    sha=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\x00"+raw).hexdigest()
    return {"sha":sha,"size":len(raw),"encoding":"base64",
            "content":base64.b64encode(raw).decode("ascii")}


class GitHubLargeCatalogTests(unittest.TestCase):
    def test_small_inline_sha_verified(self):
        entry=fixture({"episodes":[{"id":"original"}]})
        self.assertEqual(decode_catalog(entry,lambda _:None)["episodes"][0]["id"],
                         "original")

    def test_1mb_file_requires_matching_exact_git_blob(self):
        original=fixture({"episodes":[],"padding":"x"*1_100_000})
        contents=dict(original,encoding="none",content="")
        calls=[]
        def fetch(sha):
            calls.append(sha)
            return original
        self.assertEqual(decode_catalog(contents,fetch)["episodes"],[])
        self.assertEqual(calls,[contents["sha"]])
        with self.assertRaisesRegex(RuntimeError,"PINNED_BLOB_MISMATCH"):
            decode_catalog(contents,lambda _:dict(original,sha="0"*40))
        with self.assertRaisesRegex(RuntimeError,"PINNED_BLOB_MISMATCH"):
            decode_catalog(contents,lambda _:dict(original,size=2))

    def test_bad_sha_size_and_missing_content_fail_closed(self):
        entry=fixture({"episodes":[]})
        with self.assertRaisesRegex(RuntimeError,"SHA_OR_SIZE"):
            decode_catalog(dict(entry,sha="bad"),lambda _:None)
        with self.assertRaisesRegex(RuntimeError,"BYTES_CHANGED"):
            decode_catalog(dict(entry,size=entry["size"]+1),lambda _:None)
        with self.assertRaisesRegex(RuntimeError,"GIT_SHA_MISMATCH"):
            changed=base64.b64decode(entry["content"]).replace(
                b"episodes",b"episodex")
            decode_catalog(dict(entry,content=base64.b64encode(
                changed).decode("ascii")),lambda _:None)
        with self.assertRaisesRegex(RuntimeError,"UNEXPECTED_EMPTY"):
            decode_catalog(dict(entry,content="",encoding="none"),lambda _:None)

    def test_truncated_large_or_wrong_shape_cannot_refill(self):
        original=fixture({"episodes":[],"padding":"x"*1_100_000})
        contents=dict(original,content="",encoding="none")
        with self.assertRaises(RuntimeError):
            decode_catalog(contents,lambda _:dict(original,content="!!"))
        with self.assertRaisesRegex(RuntimeError,"EPISODES_INVALID"):
            decode_catalog(fixture({"not_episodes":[]}),lambda _:None)


if __name__ == "__main__":
    unittest.main()
