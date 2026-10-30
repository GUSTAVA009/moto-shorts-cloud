import unittest,os,base64,json
from unittest.mock import patch
import stop_rejected_v4 as m
from buffer_autopublish import CHANNEL

def ref(body):
    return {"sha":"sha", "content":base64.b64encode(json.dumps(body).encode()).decode()}
def data():
    def lookup(path):
        if "render-receipts/" in path:
            return ref({"voice_profile":m.OLD_VOICE,"run_id":"40991345752"})
        return ref({"episode":m.EPISODE,"buffer_post_id":m.POST_ID,"state":"queued"})
    return lookup

class StopBadVoiceTests(unittest.TestCase):
    @patch.dict(os.environ,{"GITHUB_REPOSITORY":"GUSTAVA009/moto-shorts-cloud"})
    def test_only_one_exact_queued_post_may_be_deleted(self):
        saved=[]
        def fetch(query):
            if query.startswith("query"):
                return {"post":{"id":m.POST_ID,"status":"scheduled","channelId":CHANNEL,
                        "dueAt":"2099-01-01T00:00:00Z","allowedActions":["deletePost"]}}
            saved.append(query)
            return {"deletePost":{"id":m.POST_ID}}
        out=m.cancel(fetch=fetch,lookup=data(),save=lambda *x: saved.append(x))
        self.assertEqual(out,"cancelled")
        self.assertEqual(len(saved),2)
        self.assertIn("deletePost(",saved[0])
        self.assertEqual(saved[1][1]["state"],"cancelled_rejected_v4")

    @patch.dict(os.environ,{"GITHUB_REPOSITORY":"GUSTAVA009/moto-shorts-cloud"})
    def test_sent_or_wrong_channel_never_removed(self):
        for status,channel in [("sent",CHANNEL),("scheduled","wrong")]:
            calls=[]
            def fetch(q):
                calls.append(q)
                return {"post":{"id":m.POST_ID,"channelId":channel,
                        "status":status,"dueAt":"2099-01-01T00:00:00Z",
                        "allowedActions":["deletePost"]}}
            if channel=="wrong":
                with self.assertRaises(RuntimeError):
                    m.cancel(fetch=fetch,lookup=data(),save=lambda *a:None)
            else:
                self.assertEqual(m.cancel(fetch=fetch,lookup=data(),save=lambda *a:None),"not_scheduled")
            self.assertEqual(len(calls),1)

if __name__=="__main__":
    unittest.main()
