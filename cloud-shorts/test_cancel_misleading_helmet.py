import unittest
from datetime import datetime,timezone,timedelta
import cancel_misleading_helmet as m

NOW=datetime(2026,10,30,8,18,tzinfo=timezone.utc)
def sample():
    e={"id":m.SLUG,"title":"Шлем на мотоцикле",
       "footage":[
          {"key":"a","source_page":"https://www.pexels.com/video/motorcycle-123456/",
           "source_title":"motorcycle riding"},
          {"key":"b","source_page":"https://www.pexels.com/video/motorbike-123457/",
           "source_title":"man holding motorcycle handlebars"}],
       "shots":[{"source":"a"},{"source":"b"}]}
    p={"id":m.EXPECTED_ID,"channelId":m.CHANNEL,"status":"scheduled",
       "dueAt":"2026-10-30T09:30:00Z","allowedActions":["deletePost"]}
    r={"episode":m.SLUG,"buffer_post_id":m.EXPECTED_ID,"state":"queued",
       "due_at":"2026-10-30T09:30:00Z"}
    return e,p,r
class CancelTests(unittest.TestCase):
    def test_cancel_only_single_known_future_scheduled_visual_mismatch(self):
        e,p,r=sample()
        self.assertTrue(m.may_cancel(p,r,e,NOW))
        for bad in (dict(p,status="sent"),dict(p,id="another"),
                    dict(p,channelId="someone-else"),
                    dict(p,allowedActions=[]),dict(p,dueAt="2026-10-30T08:15:00Z")):
            with self.subTest(bad=bad):
                self.assertFalse(m.may_cancel(bad,r,e,NOW))
        self.assertFalse(m.may_cancel(p,dict(r,state="sent"),e,NOW))
    def test_corrected_helmet_video_not_cancelled(self):
        e,p,r=sample()
        e["footage"][0]["source_title"]="man fastening motorcycle helmet"
        self.assertFalse(m.may_cancel(p,r,e,NOW))
if __name__=="__main__":
    unittest.main()
