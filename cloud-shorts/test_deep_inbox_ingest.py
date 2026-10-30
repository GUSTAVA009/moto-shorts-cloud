import hashlib,unittest
from deep_inbox_ingest import assert_candidate
class DeepInboxTests(unittest.TestCase):
    def setUp(self):
        self.episode={"id":"moto-rain-example","voice_engine":"aidocmaker_deep"}
        self.record={"episode_id":"moto-rain-example","provider":"aidocmaker.com",
                     "voice_id":"deep","narration":"Мотоцикл готов к поездке. "+"Это короткая оригинальная проверка голоса. "*5,
                     "preview_url":"https://storage.googleapis.com/adm--audio-playback--7d--public/mcp-preview/9c7659a8-7eee-4cb3-b086-d96a3890f8f9.mp3"}
    def test_exact_voice_and_identity(self):
        self.assertEqual(assert_candidate(self.record,self.episode)["voice_id"],"deep")
        for mutate in ({"voice_id":"ru_alexandr"},{"provider":"unknown"},
                       {"preview_url":"https://untrusted.example/a.mp3"},
                       {"episode_id":"moto-unrelated"}):
            with self.subTest(mutate=mutate):
                with self.assertRaises(ValueError):
                    assert_candidate(dict(self.record,**mutate),self.episode)
if __name__=="__main__":unittest.main()
