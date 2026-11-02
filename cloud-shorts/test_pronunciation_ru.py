"""User-requested pronunciation: «трек» in captions, «трэк» only in private TTS."""
import json
import unittest
from unittest.mock import patch

from pronunciation_ru import FORMS, to_speech_text
import voice_failover as v
from voice_qa import tokens, score

class TrackPronunciationTests(unittest.TestCase):
    def test_hard_vowel_only_in_spoken_forms(self):
        phrase=("На треке байкер. Трек и треки. До трека, по треку, "
                "с треком, из треков, о треках. ТРЕК!")
        result=to_speech_text(phrase)
        self.assertEqual(result, "На трэке байкер. Трэк и трэки. До трэка, "
                         "по трэку, с трэком, из трэков, о трэках. ТРЭК!")
        self.assertEqual(phrase, phrase)  # never mutate the public text
        self.assertEqual(to_speech_text(result), result)
        self.assertEqual(to_speech_text("Саундтрек, трекер, трекинг и трек-поле."),
                         "Саундтрек, трекер, трекинг и трэк-поле.")

    def test_asr_equivalence_does_not_remove_or_fake_missing_words(self):
        self.assertEqual(tokens("на трэке"), tokens("на треке"))
        self.assertNotEqual(tokens("на трэке"), tokens("на мотокроссе"))
        expected="Мотоциклист едет по треку, а другой райдер выполняет трюк на мотоцикле."
        pronounced="Мотоциклист едет по трэку, а другой райдер выполняет трюк на мотоцикле."
        self.assertTrue(score(expected, pronounced)["passed"])
        self.assertFalse(score(expected, "Мотоциклист по трэку, а другой райдер выполняет трюк на мотоцикле.")["passed"])

    def test_tts_request_uses_phonetic_text_but_cannot_change_voice_or_captions(self):
        state={"GUSTAVA_VOICE_REFERENCE_SHA256":"a"*64,
               "GUSTAVA_SELFHOSTED_TTS_ENABLED":"1",
               "GUSTAVA_VOICE_API_URL":"https://voice.hapychrust.ru/v1/audio/speech",
               "GUSTAVA_VOICE_APPROVED_HOST":"voice.hapychrust.ru",
               "GUSTAVA_VOICE_API_KEY":"gvk_"+"1"*48}
        route=v.available_routes(state,require_secret=True)[0]
        episode={"id":"test-track-pronun","narration":"Этот мотоциклист едет по треку. Другой байкер держит руль."}
        raw=b"RIFF"+"example".encode("ascii")
        class Response:
            headers={"X-Audio-SHA256":__import__("hashlib").sha256(raw).hexdigest(),
                     "X-Reference-SHA256":"a"*64, "X-Voice-ID":v.VOICE_ID,
                     "X-Channel-ID":v.CHANNEL_SLUG}
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def geturl(self):return route.url
            def read(self,n):return raw
        class Opener:
            def open(self,request,timeout):
                payload=json.loads(request.data.decode("utf8"))
                self.payload=payload
                self.assert_authorization=request.headers.get("Authorization")
                return Response()
        opener=Opener()
        self.assertEqual(v._post(route,episode,state,opener=opener)[0],raw)
        self.assertIn("по трэку",opener.payload["text"])
        self.assertEqual(opener.payload["voice"],v.VOICE_ID)
        self.assertIn("по треку",episode["narration"])
        self.assertEqual(opener.payload["channel_slug"],v.CHANNEL_SLUG)
