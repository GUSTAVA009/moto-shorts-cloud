"""Strict GitHub catalog reader for real >1MB Contents API responses.

For large files GitHub returns encoding='none' and empty content, even though
the actual Git object exists. Fetch that exact SHA address instead of treating
missing bytes as an empty production queue. Never proceed on tampering.
"""
import base64
import binascii
import hashlib
import json
import re


def decode_catalog(contents_entry, fetch_blob):
    if not isinstance(contents_entry, dict):
        raise RuntimeError("CATALOG_CONTENTS_ENTRY_INVALID")
    sha = str(contents_entry.get("sha") or "")
    size = contents_entry.get("size")
    if (not re.fullmatch(r"[0-9a-f]{40}", sha)
            or type(size) is not int
            or not 4 <= size <= 12_000_000):
        raise RuntimeError("CATALOG_SHA_OR_SIZE_INVALID")
    source = contents_entry
    if contents_entry.get("encoding") == "none" and not contents_entry.get("content"):
        if size < 1_000_000:
            raise RuntimeError("CATALOG_UNEXPECTED_EMPTY_CONTENTS")
        source = fetch_blob(sha)
        if (not isinstance(source,dict)
                or source.get("sha") != sha
                or source.get("size") != size
                or source.get("encoding") != "base64"):
            raise RuntimeError("CATALOG_PINNED_BLOB_MISMATCH")
    if source.get("encoding") != "base64" or not isinstance(source.get("content"),str):
        raise RuntimeError("CATALOG_BASE64_MISSING")
    try:
        raw=base64.b64decode("".join(source["content"].split()),validate=True)
    except (ValueError,TypeError,binascii.Error) as exc:
        raise RuntimeError("CATALOG_BASE64_INVALID") from exc
    if len(raw) != size:
        raise RuntimeError("CATALOG_BYTES_CHANGED")
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") +
                          b"\x00" + raw).hexdigest()
    if actual != sha:
        raise RuntimeError("CATALOG_GIT_SHA_MISMATCH")
    try:
        catalog=json.loads(raw)
    except (ValueError,UnicodeDecodeError) as exc:
        raise RuntimeError("CATALOG_JSON_INVALID") from exc
    if not isinstance(catalog,dict) or not isinstance(catalog.get("episodes"),list):
        raise RuntimeError("CATALOG_EPISODES_INVALID")
    return catalog
