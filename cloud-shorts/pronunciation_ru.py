"""Russian speech-only phonetics; never rewrite editorial text or captions.

Only owner-reported hard-E loanword "трек" is modified for private Qwen
synthesis. It is an experimental pronunciation direction, NOT acoustic proof.
Independent ASR still checks original canonical text; human listens to WAV.
"""
from __future__ import annotations
import re

LEXICON_VERSION = "ru-owner-track-1"
# The user's required audible hard consonant/vowel is represented by "э"
# only for this exact inflection set. We do NOT rewrite arbitrary "е" to "э".
FORMS = {
    "трек": "трэк",
    "трека": "трэка",
    "треку": "трэку",
    "треке": "трэке",
    "треком": "трэком",
    "треки": "трэки",
    "треков": "трэков",
    "треками": "трэками",
    "треках": "трэках",
}
_WORD = re.compile(r"(?<![\w])(" + "|".join(
    sorted(map(re.escape, FORMS), key=len, reverse=True)
) + r")(?![\w])", re.IGNORECASE | re.UNICODE)


def to_speech_text(editorial_text: str) -> str:
    """Produce phonetic TTS input while preserving published Cyrillic spelling.

    Applied ONLY to explicitly approved self-hosted narrator requests.
    Case and punctuation are preserved. Never changes names, links or words
    merely containing the substring "трек" (трекер, саундтрек, etc.).
    """
    if not isinstance(editorial_text, str):
        raise TypeError("SPEECH_TEXT_EXPECTS_STRING")
    def replace(match):
        original = match.group(0)
        spoken = FORMS[original.casefold()]
        if original.isupper():
            return spoken.upper()
        if original[0].isupper():
            return spoken[0].upper() + spoken[1:]
        return spoken
    return _WORD.sub(replace, editorial_text)
