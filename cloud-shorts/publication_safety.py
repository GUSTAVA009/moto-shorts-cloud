"""Provider-independent checks of one original, licensed, intelligible Shorts MP4.

The quality gate belongs to GUSTAVA Enduro, not a publishing vendor.
Keep historical provider receipts only for deduplication.
"""
import hashlib
from pathlib import Path

from channel_focus import assert_motorcycle_episode


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1048576), b""):
            h.update(block)
    return h.hexdigest()



def publication_allowed(episode, meta, qa, video):
    if not episode.get("auto_publish") is True:
        raise ValueError("This episode was not explicitly queued for automatic release")
    assert_motorcycle_episode(episode)
    if meta.get("episode_id") != episode["id"] or qa.get("episode_id") != episode["id"]:
        raise ValueError("Metadata/ASR episode mismatch; do not upload")
    if qa.get("passed") is not True or qa.get("status") != "passed":
        raise ValueError("Russian voice QA incomplete: no automatic release")
    if (qa.get("lexical_coverage", 0) < .97 or qa.get("ending_coverage", 0) < .95
            or qa.get("final_word_present") is not True):
        raise ValueError("Missing or clipped Russian narration")
    mix = qa.get("mixed_audio")
    if (not isinstance(mix, dict) or mix.get("episode_id") != episode["id"]
            or mix.get("source") != "FINAL_MIXED_MP4"
            or mix.get("passed") is not True or mix.get("final_word_present") is not True
            or mix.get("lexical_coverage", 0) < .97
            or mix.get("numerics_match") is not True):
        raise ValueError("Final MP4 mixed Russian narration QA failed")
    if not video.is_file() or not 100000 <= video.stat().st_size <= 150*1024*1024:
        raise ValueError("Invalid MP4 file or unexpected size")
    if video.suffix.lower() != ".mp4" or not meta.get("title") or not meta.get("description"):
        raise ValueError("Invalid upload metadata")
    if mix.get("mp4_sha256") != file_sha256(video):
        raise ValueError("Final MP4 does not match its independent mixed-audio QA proof")
    if len(meta["title"]) > 100 or any(s in meta["description"].lower() for s in ("https://", "www.")):
        raise ValueError("Illegal title or external links in description")
    if not episode.get("footage") or any(s.get("license") != "Pexels License"
                                      for s in episode["footage"]):
        raise ValueError("Unverified commercial footage rights")
    series = episode.get("episode_series")
    if series and series.get("historical_reconstruction"):
        refs = episode.get("editorial_references") or []
        if (len(set(refs)) < 2 or any(not str(u).startswith("https://") for u in refs)
                or "иллюстративные" not in meta["description"].casefold()):
            raise ValueError("Real-event documentary lacks independent sources or illustration disclosure")
    return True


