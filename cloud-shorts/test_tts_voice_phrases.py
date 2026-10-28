"""Offline tests for spoken Russian phrase boundaries and true PCM silence."""
import tempfile
from pathlib import Path
import unittest
import wave
import tts_voice as t


class RussianPhrasesTests(unittest.TestCase):
    def test_break_only_at_semantic_punctuation(self):
        s="Сначала проверим мотор. Затем — колёса, тормоза и свет. Поехали?"
        parts=t.split_phrases(s)
        self.assertEqual(parts,["Сначала проверим мотор.","Затем — колёса,","тормоза и свет.","Поехали?"])
        self.assertNotIn("Сначала",parts)

    def test_no_break_inside_abbreviations_without_space(self):
        self.assertEqual(t.split_phrases("БМВ Р60/6, мотоцикл 1982 года."),
                         ["БМВ Р60/6,","мотоцикл 1982 года."])

    def test_wav_join_has_real_zero_pcm_gap(self):
        with tempfile.TemporaryDirectory() as path:
            root=Path(path)
            pairs=[]
            for index,phrase in enumerate(["Привет.","Мир!"]):
                p=root/("phrase"+str(index)+".wav")
                with wave.open(str(p),"wb") as w:
                    w.setnchannels(1);w.setsampwidth(2);w.setframerate(22050)
                    w.writeframes(b"\x01\x00" * 1000)
                pairs.append((p,phrase))
            target=root/"joined.wav"
            t.join_phrases(pairs,target)
            with wave.open(str(target),"rb") as w:
                pcm=w.readframes(w.getnframes())
                self.assertEqual(w.getnframes(),2000+int(22050*.27))
                self.assertIn(b"\x00"*120,pcm)


if __name__=="__main__":
    unittest.main()
