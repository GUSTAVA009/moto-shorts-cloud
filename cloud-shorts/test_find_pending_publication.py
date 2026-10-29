"""Offline tests of the resumable publishing candidate selector."""
import unittest
import find_pending_publication as q


class BacklogTests(unittest.TestCase):
    def test_only_new_unpublished_qa_passed_artifacts(self):
        catalog={"episodes":[{"id":"a-new-01","auto_publish":True,"voice_engine":"kokoro_ru_dima"},
                             {"id":"old-ep-02","auto_publish":False}]}
        receipts=[{"id":"a-new-01","state":"preview_ready","voice_qa_passed":True,"mixed_audio_qa_passed":True,"run_id":"42"},
                  {"id":"old-ep-02","state":"preview_ready","voice_qa_passed":True,"mixed_audio_qa_passed":True,"run_id":"51"}]
        assets=[{"name":"daily-preview-a-new-01-42","expired":False},
                {"name":"daily-preview-old-ep-02-51","expired":False}]
        self.assertEqual(q.select(catalog,receipts,set(),assets),(42,"a-new-01","daily-preview-a-new-01-42"))
        self.assertIsNone(q.select(catalog,receipts,{"a-new-01"},assets))

    def test_retired_robotic_voice_cannot_publish_even_if_old_qa_passed(self):
        catalog={"episodes":[{"id":"piper-old","auto_publish":True,"voice_engine":"piper_ru"}]}
        receipts=[{"id":"piper-old","state":"preview_ready",
                   "voice_qa_passed":True,"mixed_audio_qa_passed":True,"run_id":"20"}]
        assets=[{"name":"daily-preview-piper-old-20","expired":False}]
        self.assertIsNone(q.select(catalog,receipts,set(),assets))

    def test_absent_qa_receipt_or_expired_artifact_refused(self):
        catalog={"episodes":[{"id":"a-new-01","auto_publish":True,"voice_engine":"kokoro_ru_dima"}]}
        rs=[{"id":"a-new-01","state":"preview_ready","run_id":"42"}]
        assets=[{"name":"daily-preview-a-new-01-42","expired":False}]
        self.assertIsNone(q.select(catalog,rs,set(),assets))
        rs[0]["voice_qa_passed"]=True
        self.assertIsNone(q.select(catalog,rs,set(),assets))
        rs[0]["mixed_audio_qa_passed"]=True
        assets[0]["expired"]=True
        self.assertIsNone(q.select(catalog,rs,set(),assets))


if __name__=="__main__":
    unittest.main()
