"""Safe one-off repair of the REAL rejected 2K motorcycle MP4.

No fake render success, forged frame rejection, silent Deep switch,
duplicate published source, or public reupload is authorized by this test.
"""
import base64
from copy import deepcopy
import json
from pathlib import Path
import unittest
import preview_queue as q
from editorial_guard import validate_catalog
from native_source_preflight import require_native_sources
from source_action_evidence import require_episode_dynamic_sources
from visual_director import directed_plan

HERE=Path(__file__).resolve().parent
SLUG="moto-roadtrip-153fe6130270"


def fixture():
    d=json.loads((HERE/"episodes.json").read_text(encoding="utf8"))
    ep=next(x for x in d["episodes"] if x["id"]==SLUG)
    proof=ep["visual_revision_evidence"]
    receipt={
       "id":SLUG,"state":"preview_ready","run_id":proof["prior_run_id"],
       "attempt_count":2,"preview_fingerprint":proof["prior_preview_fingerprint"],
       "deep_source_sha256":proof["prior_deep_audio_sha256"],
       "voice_profile":ep["voice_profile"],
       "male_voice_verified":True,
       "voice_qa_passed":True,"mixed_audio_qa_passed":True,
    }
    return d,ep,receipt


class VerifiedFrameReplacementTests(unittest.TestCase):
    def test_original_private_2k_quality_gates_remain_mandatory(self):
        catalog,ep,receipt=fixture()
        validate_catalog(catalog)
        self.assertEqual(len(require_native_sources(ep,"2k")),2)
        self.assertTrue(require_episode_dynamic_sources(ep))
        self.assertEqual([x["source_page"].split("/")[-2]
                          for x in ep["footage"]],
                         ["a-group-of-motorcycle-riders-5198992",
                          "a-person-riding-a-dirt-bike-on-a-hill-26447454"])
        self.assertEqual(ep["auto_publish"],False)
        self.assertEqual(ep["deep_audio"]["source_audio_sha256"],
                         receipt["deep_source_sha256"])
        # Real first and second originals fit the FULL 12.53s timeline
        # without repeating, freezing, or upscaling a single source.
        scenes=directed_plan(ep,{"clip_0":15.0,"clip_1":7.7},12.53)
        self.assertEqual([x["source"] for x in scenes],["clip_0","clip_1"])
        self.assertAlmostEqual(scenes[0]["seconds"],5.12,places=2)
        self.assertAlmostEqual(sum(x["seconds"] for x in scenes),12.53,places=2)

    def test_one_off_sha_attested_private_retry_is_eligible(self):
        _,ep,receipt=fixture()
        fingerprint=q.preview_fingerprint(ep)
        self.assertNotEqual(fingerprint,receipt["preview_fingerprint"])
        self.assertTrue(q.eligible_independently_rejected_scene_repair(
            ep,receipt,fingerprint))
        self.assertTrue(q.eligible_retry(ep,receipt,fingerprint))

    def test_forgeries_or_public_video_are_never_retried(self):
        _,ep,receipt=fixture()
        fp=q.preview_fingerprint(ep)
        variations=[
            ("public",lambda e,r:e.__setitem__("auto_publish",True)),
            ("no_revision",lambda e,r:e.__setitem__("visual_revision_requested",False)),
            ("wrong_deep",lambda e,r:e["deep_audio"].__setitem__("source_audio_sha256","f"*64)),
            ("wrong_render_run",lambda e,r:e["visual_revision_evidence"].__setitem__("prior_run_id","42400239824")),
            ("wrong_old_fingerprint",lambda e,r:e["visual_revision_evidence"].__setitem__("prior_preview_fingerprint","0"*64)),
            ("same_old_shot",lambda e,r:e["visual_revision_evidence"].__setitem__("replacement_source_id","5207054")),
            ("changed_second_shot",lambda e,r:e["footage"][1].__setitem__("url","https://www.pexels.com/download/video/99999999/")),
            ("tamper_sha",lambda e,r:e["footage"][0].__setitem__("native_4k_sha256","0"*64)),
            ("unverified_moto",lambda e,r:e["footage"][0].__setitem__("native_4k_width",1024)),
            ("attempt_exhausted",lambda e,r:r.__setitem__("attempt_count",3)),
            ("no_final_audio_qa",lambda e,r:r.__setitem__("mixed_audio_qa_passed",False)),
            ("wrong_speaker",lambda e,r:r.__setitem__("voice_profile","silero")),
        ]
        for label,change in variations:
            e,r=deepcopy(ep),dict(receipt)
            change(e,r)
            with self.subTest(label=label):
                self.assertFalse(q.eligible_independently_rejected_scene_repair(e,r,fp))

    def test_signed_rejection_is_fetched_and_verified_before_reservation(self):
        _,ep,receipt=fixture()
        record={"episode":SLUG,"run_id":receipt["run_id"],
             "status":"needs_new_verified_visuals",
             "reason":"FRAME_MODEL_REJECTED_ACTION_OR_NARRATION"}
        entry={"sha":ep["visual_revision_evidence"]["rejection_receipt_blob_sha"],
               "content":base64.b64encode(json.dumps(record).encode()).decode()}
        get=lambda path:entry
        self.assertTrue(q.independently_verified_rejection_receipt(
            ep,receipt,get=get))
        self.assertFalse(q.independently_verified_rejection_receipt(
            ep,receipt,get=lambda path:dict(entry,sha="0"*40)))
        forged=dict(record,status="passed")
        self.assertFalse(q.independently_verified_rejection_receipt(
            ep,receipt,get=lambda path:dict(entry,content=base64.b64encode(
                json.dumps(forged).encode()).decode())))
        self.assertFalse(q.independently_verified_rejection_receipt(
            ep,None,get=get))


if __name__=="__main__":
    unittest.main()
