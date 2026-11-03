"""Owner-LTX production intake tests. No external calls or stock source scraping."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import moto_assets as assets
import original_generated_source as original
import source_story as stories
import render_episode


def example(action, fill, batch="20261103034102-aabbcc"):
    sha = fill * 64
    size = 452000
    return {
        "key":"gustava_original_"+sha[:16],
        "source_page":assets.ORIGINAL_ASSET_ROOT+"/meta/"+sha+".json",
        "url":assets.ORIGINAL_ASSET_ROOT+"/clips/"+sha+".mp4",
        "author":assets.ORIGINAL_AUTHOR,
        "license":assets.ORIGINAL_LICENSE,
        "generation_model":assets.ORIGINAL_MODEL,
        "generation_batch":batch,
        "original_sha256":sha,
        "file_size":size,
        "duration":6.71,
        "scene_action":action,
        "source_title":"motorcycle "+action+" in a generated original scene",
        "prompt":"Fully new photorealistic action from LTX Video",
    }


class Response(io.BytesIO):
    def __init__(self, content, url):
        super().__init__(content)
        self.original_url=url
    def geturl(self):
        return self.original_url


class OwnerOriginalMediaTests(unittest.TestCase):
    def setUp(self):
        original.verified_feed.cache_clear()
        self.first=example("riding","a")
        self.second=example("jump","b")

    def tearDown(self):
        original.verified_feed.cache_clear()

    def test_storyboard_clip_key_keeps_original_source_sha_identity(self):
        for i,src in enumerate((self.first,self.second)):
            episode_source=dict(src,key="clip_"+str(i))
            self.assertEqual(assets.source_id(episode_source),
                             assets.source_id(src))
            self.assertEqual(assets.validated_media(episode_source),
                             assets.source_id(src))
        with self.assertRaisesRegex(ValueError,"SHA_MANIFEST_ID_INVALID"):
            assets.validated_media(dict(self.first,key="stock_lookalike"))

    def test_clickbait_verb_ceplyaet_does_not_invent_motorcycle_chain(self):
        from visual_director import main_subject
        self.assertIsNone(main_subject({"title":
            "Мотопрыжок или поездка: какой кадр цепляет сильнее? #shorts"}))
        self.assertEqual(main_subject({"title":"Проверь цепь мотоцикла"}),
                         "chain")

    def test_fixed_owner_origin_licenses_and_sha_are_never_inferred(self):
        for item in (self.first,self.second):
            self.assertEqual(assets.source_id(item),
                             "gustava-original-"+item["original_sha256"])
            self.assertEqual(assets.validated_media(item),assets.source_id(item))
        for edits in (
            {"original_sha256":"0"*64},
            {"key":"gustava_original_does-not-match"},
            {"url":"https://untrusted.example/clips/"+"a"*64+".mp4"},
            {"url":"http://84-252-66-87.sslip.io/yt-factory-originals/clips/"+"a"*64+".mp4"},
            {"license":"Pexels License"},
            {"author":"Some other stock creator"},
            {"generation_model":"unknown-unlicensed"},
            {"scene_action":"crash"},
            {"generation_batch":"not-a-batch"},
            {"file_size":0},
            {"duration":2.5},
        ):
            with self.subTest(edits=edits),self.assertRaises(ValueError):
                assets.validated_media(dict(self.first,**edits))

    def test_feed_disabled_by_default_and_rejects_untrusted_url(self):
        with patch.dict(os.environ,{"GUSTAVA_ORIGINAL_FEED_URL":""}):
            self.assertEqual(original.verified_feed(),[])
        original.verified_feed.cache_clear()
        with patch.dict(os.environ,{"GUSTAVA_ORIGINAL_FEED_URL":"https://evil.test/index.json"}):
            with self.assertRaisesRegex(ValueError,"NOT_OWNER_CONTROLLED"):
                original.verified_feed()

    def test_fresh_real_owner_pair_makes_filmable_two_scene_russian_story(self):
        feed=json.dumps({"version":1,"provider":"gustava-ltx-original",
                         "sources":[self.first,self.second]}).encode("utf8")
        with patch.dict(os.environ,{"GUSTAVA_ORIGINAL_FEED_URL":assets.ORIGINAL_FEED_URL}):
            with patch.object(original.urllib.request,"urlopen",
                              return_value=Response(feed,assets.ORIGINAL_FEED_URL)):
                self.assertEqual(len(original.verified_feed()),2)
                self.assertEqual(len(original.original_results(("motocross",))),2)
                pair=stories.select_pair(original.original_results(("motocross",)),set())
                self.assertEqual(len(pair),2)
                self.assertEqual({x["scene_action"] for x in pair},{"riding","jump"})
                self.assertTrue(stories.same_owner_original_pair(*pair))
                narration=stories.compose(pair,[])
                self.assertEqual(len(stories.require_filmable(narration,pair)),2)
                self.assertTrue(125<=len(narration["narration"])<=300)
                self.assertEqual(len(original.verified_feed()),2)

    def test_original_mixed_topic_actions_retain_both_real_mp4s(self):
        # These source pairs used to be silently dropped because neither
        # action pair fits the same stock-catalog topic exactly.
        for left,right,topic in (
            ("repair","helmet","repair"),
            ("city","forest","city"),
            ("wheel","riding","training"),
            ("rain","forest","rain"),
        ):
            with self.subTest(pair=(left,right)):
                original.verified_feed.cache_clear()
                first=example(left,"a")
                second=example(right,"b")
                feed=json.dumps({
                    "version":1,"provider":"gustava-ltx-original",
                    "sources":[first,second]}).encode("utf8")
                with patch.dict(os.environ,{
                        "GUSTAVA_ORIGINAL_FEED_URL":assets.ORIGINAL_FEED_URL}):
                    with patch.object(original.urllib.request,"urlopen",
                                      return_value=Response(feed,assets.ORIGINAL_FEED_URL)):
                        selected=original.original_results(topic)
                        self.assertEqual({x["scene_action"] for x in selected},
                                         {left,right})
                        self.assertEqual(len(selected),2)
                        self.assertEqual(original.original_results(
                            topic,{assets.source_id(first)}),[])

    def test_batch_coherence_cannot_be_faked_with_another_job(self):
        original.verified_feed.cache_clear()
        changed=example("jump","b",batch="20261103035102-ddffee")
        feed=json.dumps({"version":1,"provider":"gustava-ltx-original",
                         "sources":[self.first,changed]}).encode()
        with patch.dict(os.environ,{"GUSTAVA_ORIGINAL_FEED_URL":assets.ORIGINAL_FEED_URL}):
            with patch.object(original.urllib.request,"urlopen",
                              return_value=Response(feed,assets.ORIGINAL_FEED_URL)):
                self.assertEqual(original.original_results("motocross"),[])
                self.assertFalse(stories.same_owner_original_pair(self.first,changed))
                self.assertEqual(stories.select_pair([self.first,changed],set()),[])

    def test_repeated_clip_and_same_action_never_create_one_original(self):
        for clips in ((self.first,self.first),(self.first,example("riding","b"))):
            original.verified_feed.cache_clear()
            feed=json.dumps({"version":1,"provider":"gustava-ltx-original",
                             "sources":list(clips)}).encode()
            with patch.dict(os.environ,{"GUSTAVA_ORIGINAL_FEED_URL":assets.ORIGINAL_FEED_URL}):
                with patch.object(original.urllib.request,"urlopen",
                                  return_value=Response(feed,assets.ORIGINAL_FEED_URL)):
                    if clips[0]["original_sha256"]==clips[1]["original_sha256"]:
                        with self.assertRaisesRegex(ValueError,"REPEATED_SHA"):
                            original.verified_feed()
                    else:
                        self.assertEqual(original.original_results("training"),[])

    def test_sha_binds_original_mp4_bytes_before_render(self):
        body=b"original-ltx-test-bytes-"*25000
        media=example("riding","a")
        sha=hashlib.sha256(body).hexdigest()
        media.update(original_sha256=sha,key="gustava_original_"+sha[:16],
                     source_page=assets.ORIGINAL_ASSET_ROOT+"/meta/"+sha+".json",
                     url=assets.ORIGINAL_ASSET_ROOT+"/clips/"+sha+".mp4",
                     file_size=len(body))
        with tempfile.TemporaryDirectory() as root:
            target=Path(root)/"clip_0.mp4"
            def download_bytes(*args,**kwargs):
                return Response(body,media["url"])
            with patch.object(render_episode.urllib.request,"urlopen",
                              side_effect=download_bytes),patch.object(
                       render_episode,"probe",
                       return_value=(media["duration"],[{"codec_type":"video"}])):
                render_episode.download(media,target,required_seconds=6)
                self.assertEqual(target.read_bytes(),body)
                target.unlink()
                bad=dict(media,original_sha256="f"*64,
                         key="gustava_original_"+"f"*16,
                         source_page=assets.ORIGINAL_ASSET_ROOT+"/meta/"+"f"*64+".json",
                         url=assets.ORIGINAL_ASSET_ROOT+"/clips/"+"f"*64+".mp4")
                with self.assertRaisesRegex(RuntimeError,"SHA_SIZE_MISMATCH"):
                    render_episode.download(bad,target,required_seconds=6)
                self.assertFalse(target.exists())


if __name__=="__main__":
    unittest.main()
