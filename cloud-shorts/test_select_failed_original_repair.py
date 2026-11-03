"""Offline tests of private immutable failed-ASR repair selection."""
import base64
import copy
import json
from pathlib import Path
import unittest

import select_failed_original_repair as pick
import preview_queue


class SelectFailedOriginalVoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data=json.loads((Path(__file__).parent/"episodes.json").read_text("utf8"))
        cls.ep=next(x for x in data["episodes"]
                    if x["id"]=="moto-training-5d7cc0e964be")

    def fixture(self):
        ep=copy.deepcopy(self.ep)
        receipt={
            "id":ep["id"],"state":"preview_ready",
            "attempt_count":1,"run_id":"41549749487",
            "preview_fingerprint":preview_queue.preview_fingerprint(ep),
            "selfhosted_reference_sha256":
                "76d834646534a0463889a824895a1e54ce5ed672b2dda46babba151b32a63aef",
            "voice_qa_passed":False,"mixed_audio_qa_passed":False,
        }
        calls=[]
        def fake(method,path):
            calls.append((method,path))
            if path.startswith("contents/render-receipts/"):
                return {"sha":"x","content":base64.b64encode(
                    json.dumps(receipt).encode()).decode()}
            if path=="actions/runs/41549749487":
                return {"status":"completed","conclusion":"failure"}
            if path=="actions/runs/41549749487/artifacts?per_page=100":
                return {"total_count":1,"artifacts":[{
                    "name":"daily-preview-"+ep["id"]+"-41549749487",
                    "expired":False,"size_in_bytes":3527620}]}
            raise AssertionError("Unexpected GET "+path)
        return ep,receipt,calls,fake

    def test_selects_only_real_failed_owned_original_unpublished_artifact(self):
        ep,receipt,calls,api=self.fixture()
        paths=["render-receipts/"+ep["id"]+".json"]
        chosen=pick.select_one([ep],paths,api)
        self.assertEqual(chosen,{"episode":ep["id"],
                                  "run_id":"41549749487",
                                  "artifact_name":"daily-preview-"+ep["id"]+"-41549749487"})
        self.assertTrue(all(method=="GET" for method,_ in calls))
        self.assertIsNone(pick.select_one([ep],paths,api,
                                           requested_run_id="41441218792"))
        self.assertIsNotNone(pick.select_one([ep],paths,api,
                                              requested_run_id="41549749487"))

    def test_no_public_or_mismatched_or_already_revised_original_repair(self):
        ep,receipt,calls,api=self.fixture()
        path="render-receipts/"+ep["id"]+".json"
        self.assertIsNone(pick.select_one([ep],[path,
            "buffer-publication-receipts/"+ep["id"]+".json"],api))
        receipt["attempt_count"]=2
        self.assertIsNone(pick.select_one([ep],[path],api))
        receipt["attempt_count"]=1
        ep["voice_revision_requested"]=True
        self.assertIsNone(pick.select_one([ep],[path],api))
        ep["voice_revision_requested"]=False
        ep["auto_publish"]=True
        self.assertIsNone(pick.select_one([ep],[path],api))

    def test_never_repair_successful_mp4_or_mismatched_older_run(self):
        ep,receipt,calls,api=self.fixture()
        path="render-receipts/"+ep["id"]+".json"
        receipt["voice_qa_passed"]=True
        self.assertIsNone(pick.select_one([ep],[path],api))
        receipt["voice_qa_passed"]=False
        receipt["selfhosted_reference_sha256"]="0"*64
        self.assertIsNone(pick.select_one([ep],[path],api))


if __name__=="__main__":
    unittest.main()
