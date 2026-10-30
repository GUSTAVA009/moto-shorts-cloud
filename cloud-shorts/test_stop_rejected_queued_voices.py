import os,unittest,base64,json
from datetime import datetime,timezone
from unittest.mock import patch
import stop_rejected_queued_voices as x
from buffer_autopublish import CHANNEL

def encoded(doc):
    return {"sha":"sha","content":base64.b64encode(json.dumps(doc).encode()).decode()}

class CancelOldVoiceScheduledTests(unittest.TestCase):
    def test_old_scheduled_future_may_be_cancelled_only_if_exact_receipt(self):
        ep="moto-forest-4bd53e13fec4"
        post={"id":x.TARGETS[ep],"channelId":CHANNEL,
              "status":"scheduled","dueAt":"2099-01-01T09:30:00Z",
              "allowedActions":["deletePost"]}
        receipt={"episode":ep,"buffer_post_id":post["id"],
                 "state":"queued","due_at":post["dueAt"]}
        old={"id":ep,"voice_profile":"gustava_native_bass_baritone_v6"}
        now=datetime(2026,10,30,tzinfo=timezone.utc)
        self.assertTrue(x.eligible(post,receipt,old,ep,post["id"],now))
        self.assertFalse(x.eligible(dict(post,status="sent"),receipt,old,ep,post["id"],now))
        self.assertFalse(x.eligible(dict(post,status="sending"),receipt,old,ep,post["id"],now))
        self.assertFalse(x.eligible(dict(post,allowedActions=[]),receipt,old,ep,post["id"],now))
        self.assertFalse(x.eligible(post,receipt,
            dict(old,voice_profile="gustava_create_audio_deep_v1"),ep,post["id"],now))
        with self.assertRaises(RuntimeError):
            x.eligible(dict(post,channelId="wrong"),receipt,old,ep,post["id"],now)
        with self.assertRaises(RuntimeError):
            x.eligible(post,dict(receipt,buffer_post_id="bad"),old,ep,post["id"],now)

    @patch.dict(os.environ,{"GITHUB_REPOSITORY":"GUSTAVA009/moto-shorts-cloud"})
    def test_live_scheduled_only_cancelled_once_no_sent_posts_ever(self):
        saved=[];mutations=[];now=datetime(2026,10,30,tzinfo=timezone.utc)
        selected="moto-forest-4bd53e13fec4"
        def read(path):
            slug=Path(path).stem
            if slug!=selected:
                return None
            if path.startswith("render-receipts/"):
                return encoded({"id":selected,"voice_profile":"gustava_native_bass_baritone_v6"})
            return encoded({"episode":slug,"buffer_post_id":x.TARGETS[slug],
                            "state":"queued","due_at":"2099-01-01T09:30:00Z"})
        from pathlib import Path
        def fetch(query):
            if query.startswith("query"):
                return {"post":{"id":x.TARGETS[selected],"channelId":CHANNEL,
                    "status":"scheduled","dueAt":"2099-01-01T09:30:00Z",
                    "allowedActions":["deletePost"]}}
            mutations.append(query)
            return {"deletePost":{"id":x.TARGETS[selected]}}
        changed=x.cancel(fetch=fetch,read=read,save=lambda *args:saved.append(args),now=now)
        self.assertEqual(len(changed),1)
        self.assertEqual(len(mutations),1)
        self.assertEqual(len(saved),1)
        self.assertEqual(saved[0][1]["state"],x.CANCEL_STATE)

if __name__=="__main__":
    unittest.main()
