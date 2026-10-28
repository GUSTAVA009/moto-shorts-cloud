"""Offline read-only test for the authorized Buffer channel."""
from unittest.mock import patch
import unittest
import buffer_readiness as r

ORG="a"*24

def account():
    return {"account":{"organizations":[{"id":ORG,"name":"GUSTAVA"}]}}
def channels(service="youtube",disconnected=False,locked=False,paused=False):
    return {"channels":[{"id":r.BUFFER_CHANNEL,"service":service,
                         "name":"GUSTAVA Enduro","isDisconnected":disconnected,
                         "isLocked":locked,"isQueuePaused":paused}]}
def posts(n=0):
    return {"posts":{"edges":[{"node":{"id":str(i)}} for i in range(n)],
                     "pageInfo":{"hasNextPage":False}}}

class BufferReadinessTests(unittest.TestCase):
    def test_verified_youtube_queue_is_empty(self):
        with patch.object(r,"request",side_effect=[account(),channels(),posts()]) as mocked:
            result=r.inspect()
        self.assertTrue(result["connected"])
        self.assertTrue(result["queue_has_room"])
        self.assertEqual(result["buffer_channel_id"],r.BUFFER_CHANNEL)
        self.assertEqual(mocked.call_count,3)

    def test_full_queue_is_not_ready_for_more_uploads(self):
        with patch.object(r,"request",side_effect=[account(),channels(),posts(10)]):
            result=r.inspect()
        self.assertFalse(result["queue_has_room"])

    def test_wrong_service_is_rejected(self):
        with patch.object(r,"request",side_effect=[account(),channels(service="instagram")]):
            with self.assertRaisesRegex(RuntimeError,"Wrong network"):r.inspect()

    def test_disconnected_channel_is_rejected(self):
        with patch.object(r,"request",side_effect=[account(),channels(disconnected=True)]):
            with self.assertRaisesRegex(RuntimeError,"isDisconnected"):r.inspect()

    def test_channel_not_found_is_rejected(self):
        with patch.object(r,"request",side_effect=[account(),{"channels":[]}]):
            with self.assertRaisesRegex(RuntimeError,"not found"):r.inspect()

if __name__=="__main__":unittest.main()
