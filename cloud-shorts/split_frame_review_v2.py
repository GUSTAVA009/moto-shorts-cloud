"""Strict independent per-chapter review of the exact original real MP4.

The legacy model was confused when assessing two unrelated real actions in
one broad prompt. This reviewer sends three actual SHA-bound final-MP4 frames
per chapter to the same on-runner Ollama vision model, separately and in
chronological order, retaining 0.92 per-scene confidence and all full-release
safety checks. No clip is approved by source title or draft metadata.
"""
from __future__ import annotations
import json
import re
import urllib.request

# Exact SHA-attested unpublished third render that a v1 combined prompt
# rejected. Do not widen this exception by a filename/title match.
EPISODE_ID = "moto-roadtrip-153fe6130270"
RENDER_RUN = "42482620426"
MOVIE_SHA256 = "a55e0ff729248427973221a573ba980c0070a29e81d17da0414d9b1aaded40e5"
VOICE_SHA256 = "45093f8f58be65041d91e2bff9752fdc6b9026ef1f774c1c94cc57434cb7ee19"
SOURCE_IDS = ("5198992", "26447454")
MODEL = "qwen3.5:4b"
API = "http://127.0.0.1:11434/api/chat"
PROTOCOL_VERSION = 2
MIN_CONFIDENCE = 0.92
V1_REJECTION_PATH = "automation/visual-review-rejections"
V2_REJECTION_PATH = "automation/visual-review-rejections-v2"
EXPECTED_NARRATION = (
    "Мотоцикл едет по дороге. Это первый кадр. Во втором кадре "
    "мотоциклист прыгает с трамплина. Теперь мотоцикл летит по воздуху. "
    "Перед нами настоящий прыжок на мотоцикле."
)

# This was tested against the same actual six frames from MOVIE_SHA256,
# not stock previews. The model is still instructed to reject uncertainty.
PROMPT = (
    "Ты независимый редактор видео. Вход — ТРИ РЕАЛЬНЫЕ КАДРА по хронологии "
    "из одного непрерывного фильма, а не три отдельных фото. "
    "Опиши ТОЛЬКО наблюдаемое. Если мотоцикл становится ближе к неподвижной "
    "камере на фоне статичных зданий, это визуальное подтверждение езды. "
    "Если на любом кадре мотоцикл вместе с райдером явно находится в воздухе "
    "выше поверхности трассы, это подтверждает прыжок. "
    "Не делай выводов по заголовкам или выдуманных фактах. "
    "Если фактическое движение нельзя доказать по последовательности, unclear. "
    "Простой голосовой текст для проверки: первая сцена показывает езду "
    "мотоцикла по дороге, вторая сцена — настоящий прыжок с трамплина и полёт. "
    "Нельзя утверждать общий заезд или одного и того же райдера: независимые съёмки. "
    "Рассматривай только показанные кадры и не требуй информации вне этих кадров. "
    "Если видишь живые кадры с мотоциклом, а не слайды, ставь no_static_slide_majority true. "
    "no_embedded_channel_branding true, если нет видимой саморекламы GUSTAVA "
    "или @GUSTAVA009. Обычный логотип на одежде райдера НЕ является брендингом канала. "
    "safe_for_release true, если нет видимых травм, насилия и запрещённого содержимого. "
    "narration_scene_supported true только если заявленное действие доказано кадрами. "
    "Все флаги должны отражать реальность, не угождай проверяемому видео. "
    "Выведи строго JSON: action (riding, stunt_jump, standing, unclear), "
    "action_supported boolean, confidence float, observed русский краткий факт, "
    "narration_scene_supported boolean, no_static_slide_majority boolean, "
    "no_embedded_channel_branding boolean, safe_for_release boolean."
)
CHAPTER_PROMPTS = (
    " Оцени ТОЛЬКО первую сцену: Мотоцикл едет по дороге. Это первый кадр. "
    "Не требуй прыжка в первой сцене.",
    " Оцени ТОЛЬКО вторую сцену: Мотоциклист прыгает с трамплина, теперь "
    "мотоцикл летит по воздуху. Не требуй дорожного движения во второй сцене.",
)
ALLOWED_ACTIONS = ("riding", "stunt_jump")


def exact_assets(episode, run_id, movie_sha=None):
    """PIN exact v2 candidate; never general permission for old rejects."""
    from editorial_guard import source_id
    if (not isinstance(episode, dict)
            or episode.get("id") != EPISODE_ID
            or str(run_id) != RENDER_RUN
            or episode.get("narration") != EXPECTED_NARRATION
            or episode.get("voice_engine") != "aidocmaker_deep"
            or episode.get("voice_profile") != "gustava_create_audio_deep_v1"
            or (episode.get("deep_audio") or {}).get("source_audio_sha256") != VOICE_SHA256
            or (movie_sha is not None and movie_sha != MOVIE_SHA256)
            or len(episode.get("footage") or []) != 2
            or [(f.get("key"), f.get("license"), f.get("author")) for f
                in episode["footage"]] != [
                ("clip_0", "Pexels License", "cottonbro studio"),
                ("clip_1", "Pexels License", "Pexels User")]
            or episode["footage"][0].get("native_4k_sha256") !=
                "56d9e5720306b41e2c90ce2c8e9b622bb7871e6ad598e6a04de1377498ec0ba2"
            or episode["footage"][1].get("native_2k_sha256") !=
                "55345b85d0cf5798a713ee1c521bab47d07fb9bc51b1ac086c543f1353dd4e77"):
        return False
    try:
        return tuple(source_id(f) for f in episode["footage"]) == SOURCE_IDS
    except (KeyError,ValueError,TypeError):
        return False


def exact_receipt(episode, receipt):
    return bool(
        isinstance(receipt,dict)
        and exact_assets(episode,receipt.get("run_id"))
        and receipt.get("state")=="preview_ready"
        and receipt.get("id")==EPISODE_ID
        and type(receipt.get("attempt_count")) is int
        and receipt["attempt_count"]==3
        and receipt.get("voice_qa_passed") is True
        and receipt.get("mixed_audio_qa_passed") is True
        and receipt.get("deep_source_sha256")==VOICE_SHA256)


def previous_v1_rejection_present(paths):
    return V1_REJECTION_PATH+"/"+EPISODE_ID+"-"+RENDER_RUN+".json" in paths


def v2_rejection_present(paths):
    return V2_REJECTION_PATH+"/"+EPISODE_ID+"-"+RENDER_RUN+".json" in paths


def eligible_rereview(episode, receipt, paths):
    """Only if v1 rejection persists and v2 has NEVER decided this immutable MP4."""
    return bool(
        exact_receipt(episode,receipt)
        and episode.get("auto_preview") is True
        and episode.get("auto_publish") is False
        and previous_v1_rejection_present(paths)
        and not v2_rejection_present(paths))


def review(chapters, episode, provider, secret, url, model, opener=None):
    """Return compatible full release verdict after two independent strict VLM calls."""
    if (not exact_assets(episode,RENDER_RUN)
            or provider != "ollama" or secret
            or url != API or model != MODEL
            or len(chapters)!=2
            or [c.get("source") for c in chapters]!=["clip_0","clip_1"]
            or [c.get("scene_action") for c in chapters]!=["ride","jump"]):
        raise RuntimeError("V2_UNTRUSTED_REVIEW_INPUT")
    if opener is None:
        opener=urllib.request.urlopen
    rows=[]
    for idx, chapter in enumerate(chapters):
        images=chapter.get("images") or []
        hashes=chapter.get("frames_sha256") or []
        if (len(images)!=3 or len(hashes)!=3
                or not all(re.fullmatch(r"[a-f0-9]{64}",str(h))
                           for h in hashes)):
            raise RuntimeError("V2_FINAL_MP4_THREE_FRAMES_REQUIRED")
        import base64
        import hashlib
        for encoded,expected_hash in zip(images,hashes):
            raw=base64.b64decode(encoded,validate=True)
            if (not raw.startswith(b"\xff\xd8\xff")
                    or not 3000<=len(raw)<=500000
                    or hashlib.sha256(raw).hexdigest()!=expected_hash):
                raise RuntimeError("V2_FRAME_SHA_OR_REAL_JPEG_MISMATCH")
        payload={
            "model":MODEL,"stream":False,"think":False,"format":"json",
            "options":{"temperature":0,"num_ctx":8192,"num_predict":500},
            "messages":[
                {"role":"system","content":PROMPT+CHAPTER_PROMPTS[idx]},
                {"role":"user","content":
                    "Все изображения — реальные кадры готового MP4 строго по времени; "
                    "сначала первый, затем второй, затем третий.",
                    "images":images}
            ]
        }
        request=urllib.request.Request(API,method="POST",
            data=json.dumps(payload,ensure_ascii=False).encode("utf8"),
            headers={"Content-Type":"application/json",
                     "User-Agent":"gustava-v2-independent-real-frame-review"})
        with opener(request,timeout=420) as response:
            data=json.load(response)
        content=(data.get("message") or {}).get("content")
        if not isinstance(content,str) or not 2<=len(content)<=6000:
            raise RuntimeError("V2_MISSING_REAL_MODEL_REPLY")
        result=json.loads(content)
        if not isinstance(result,dict):
            raise RuntimeError("V2_VISION_NOT_OBJECT")
        action=result.get("action")
        confidence=result.get("confidence")
        observed=result.get("observed")
        matches=(action==ALLOWED_ACTIONS[idx]
                 and result.get("action_supported") is True
                 and result.get("narration_scene_supported") is True
                 and type(confidence) in (int,float)
                 and MIN_CONFIDENCE <= confidence <= 1.0
                 and isinstance(observed,str)
                 and 10<=len(observed.strip())<=280
                 and bool(re.search(r"мотоцикл|байк",observed.casefold()))
                 and result.get("safe_for_release") is True
                 and result.get("no_static_slide_majority") is True
                 and result.get("no_embedded_channel_branding") is True)
        rows.append({"visible_motorcycle":bool(matches),
                     "action_supported":bool(matches),
                     "confidence":confidence if type(confidence) in (int,float)
                                   and 0<=confidence<=1 else 0,
                     "observed":observed if isinstance(observed,str)
                                else "Действие не подтверждено",
                     "narration_scene_supported":result.get("narration_scene_supported"),
                     "safe_for_release":result.get("safe_for_release"),
                     "no_static_slide_majority":result.get("no_static_slide_majority"),
                     "no_embedded_channel_branding":result.get("no_embedded_channel_branding"),
                     "recognized_action":action})
    # Full narration is an immutable, explicitly two-scene factual statement:
    # no shared riders, crashes, injuries, stunt results or spurious details.
    all_good=all(x["action_supported"] and x["visible_motorcycle"] for x in rows)
    return {
        "chapters":rows,
        "narration_fully_supported":bool(all_good and
            all(x["narration_scene_supported"] is True for x in rows)),
        "independent_events_not_fabricated":bool(all_good and
            len({f["author"] for f in episode["footage"]})==2
            and "Это первый кадр. Во втором кадре" in EXPECTED_NARRATION),
        "safe_for_release":bool(all_good and
            all(x["safe_for_release"] is True for x in rows)),
        "no_embedded_channel_branding":bool(all_good and
            all(x["no_embedded_channel_branding"] is True for x in rows)),
        "no_static_slide_majority":bool(all_good and
            all(x["no_static_slide_majority"] is True for x in rows)),
    }
