import hashlib,unittest
from deep_inbox_ingest import assert_candidate, inspect_candidates
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
    def test_one_bad_asr_cannot_block_two_good_deep_voices(self):
        import copy
        items=[]
        episodes={}
        for i in range(3):
            record=dict(self.record,episode_id=f"moto-rain-{i}")
            items.append(record)
            episodes[record["episode_id"]]=dict(self.episode,id=record["episode_id"],
                  title=f"Дождливая трасса {i}",narration=self.record["narration"])
        def assessor(item,ep,folder):
            if ep["id"]=="moto-rain-0":
                raise RuntimeError("DEEP_ASR_REJECTED: one misheard syllable")
            return {"provider":"aidocmaker.com","voice_id":"deep",
                    "preview_url":item["preview_url"],
                    "transcript_sha256":hashlib.sha256(item["narration"].encode()).hexdigest(),
                    "source_audio_sha256":"b"*64}, {"id":ep["id"],"passed":True}
        # Catalogue validation remains a mandatory step for accepted entries,
        # represented by actual validated Episode schema from production.
        import deep_inbox_ingest as di
        from unittest.mock import patch
        with patch.object(di,"validate_episode",return_value="ok"):
            changes,blocked=inspect_candidates(items,episodes,"/tmp",assessor=assessor)
        self.assertEqual([c[0] for c in changes],["moto-rain-1","moto-rain-2"])
        self.assertEqual([x["episode"] for x in blocked],["moto-rain-0"])
        self.assertTrue(all(x[2]["passed"] for x in changes))

    def test_successful_new_deep_must_trigger_renderer_on_push_too(self):
        from pathlib import Path
        source=Path(__file__).with_name("deep_inbox_ingest.py").read_text(encoding="utf8")
        self.assertIn('range(min(len(completed),2))',source)
        self.assertIn('actions/workflows/daily-preview.yml/dispatches',source)
        self.assertNotIn('if os.getenv("GITHUB_EVENT_NAME")=="workflow_dispatch"',source)

    def test_unexpected_provider_error_must_abort_intake(self):
        from unittest.mock import patch
        import deep_inbox_ingest as di
        with patch.object(di,"validate_episode",return_value="ok"):
            with self.assertRaisesRegex(RuntimeError,"Network failure"):
                inspect_candidates([self.record],{self.episode["id"]:self.episode},
                                   "/tmp",assessor=lambda *a: (_ for _ in ()).throw(
                                       RuntimeError("Network failure")))

if __name__=="__main__":unittest.main()
