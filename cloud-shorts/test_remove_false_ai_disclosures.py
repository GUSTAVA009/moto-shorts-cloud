import unittest
from datetime import datetime,timezone,timedelta
import remove_false_ai_disclosures as fix
from buffer_autopublish import CHANNEL

NOW = datetime(2026,10,30,5,40,tzinfo=timezone.utc)
DUE="2026-10-30T09:30:00.000Z"

def ep():
    return {"id":"forest-test","auto_publish":True,
            "voice_engine":"silero_mit_bass_baritone",
            "channel_niche":"motorcycle",
            "title":"Мотоцикл в лесу",
            "narration":"Мотоцикл в лесу и повороты.",
            "editorial":{"bike":"offroad-trail-motorcycle"},
            "footage":[{"license":"Pexels License"}]}
def post():
    return {"id":"buffer-1","channelId":CHANNEL,"status":"scheduled",
            "dueAt":DUE,"text":"Это описание","assets":[{"id":"media-1"}],
            "metadata":{"isAiGenerated":True,"title":"Мотоцикл"}}
def receipt():
    return {"buffer_post_id":"buffer-1","episode":"forest-test",
            "state":"queued","due_at":DUE}

class AiLabelRepairTests(unittest.TestCase):
    def test_only_real_stock_non_disclosure_future_scheduled_can_be_changed(self):
        self.assertTrue(fix.eligible(post(),receipt(),ep(),NOW))
        for unsafe in [
            (dict(post(), status="sent"),receipt(),ep()),
            (dict(post(), channelId="other"),receipt(),ep()),
            (dict(post(), id="wrong"),receipt(),ep()),
            (dict(post(), metadata={"isAiGenerated":False}),receipt(),ep()),
            (post(),dict(receipt(),state="cancelled"),ep()),
            (post(),receipt(),dict(ep(),realistic_synthetic_visuals=True)),
            (post(),receipt(),dict(ep(),footage=[{"license":"unknown"}])),
        ]:
            with self.subTest(unsafe=unsafe):
                self.assertFalse(fix.eligible(*unsafe,NOW))
        self.assertFalse(fix.eligible(post(),receipt(),ep(),
            datetime(2026,10,30,9,29,tzinfo=timezone.utc)))

    def test_edit_only_disclosure_bit_and_confirm_every_original_field(self):
        orig=post()
        calls=[]
        def fetch(query,values):
            calls.append((query,values))
            updated=dict(orig,metadata={"isAiGenerated":False,"title":"Мотоцикл"})
            return {"editPost":{"post":updated}}
        result=fix.patch_ai_disclosure(orig,fetch)
        self.assertFalse(result["metadata"]["isAiGenerated"])
        self.assertEqual(calls[0][1],{
            "input":{"id":"buffer-1","metadata":{"youtube":{"isAiGenerated":False}}}
        })
        self.assertNotIn("aiAssisted",calls[0][1]["input"])
        self.assertNotIn("dueAt",calls[0][1]["input"])
        self.assertNotIn("assets",calls[0][1]["input"])
        self.assertNotIn("text",calls[0][1]["input"])
        self.assertNotIn("title",calls[0][1]["input"]["metadata"]["youtube"])

    def test_malformed_response_fails_closed(self):
        with self.assertRaises(RuntimeError):
            fix.patch_ai_disclosure(post(),lambda *args:{"editPost":{"message":"denied"}})

if __name__=="__main__":
    unittest.main()
