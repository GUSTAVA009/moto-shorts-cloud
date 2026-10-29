"""Independent Russian ASR with two open-source CPU-only engines.

Faster-Whisper can fail to fetch Hugging Face CTranslate2 weights on transient
CI runners. OpenAI Whisper uses independently hosted model weights and acts as
a real fallback; neither returns success if transcription is unavailable.
"""
from __future__ import annotations
import os
from pathlib import Path


def transcribe(media,model="base"):
    media=str(media)
    if not Path(media).is_file():
        raise FileNotFoundError(media)
    failure=None
    try:
        from faster_whisper import WhisperModel
        detector=WhisperModel(model,device="cpu",compute_type="int8")
        segments,_=detector.transcribe(media,language="ru",beam_size=5,
            vad_filter=False,condition_on_previous_text=False)
        text=" ".join(x.text.strip() for x in segments).strip()
        if not text:
            raise RuntimeError("faster-whisper returned no audible Russian text")
        return text, "faster-whisper "+model+" CPU"
    except (ImportError,OSError,RuntimeError,ValueError,TimeoutError,ConnectionError) as exc:
        failure=type(exc).__name__ + ": " + str(exc)[:180]
    except Exception as exc:
        # Unknown model availability errors are recoverable, but never silently
        # turn a failed API call into a passing transcript.
        failure=type(exc).__name__ + ": " + str(exc)[:180]
    try:
        import whisper
        cache=Path(os.environ.get("RUNNER_TEMP",str(Path.home()/".cache")))/"gustava-whisper-weights"
        cache.mkdir(parents=True,exist_ok=True)
        detector=whisper.load_model(model,device="cpu",download_root=str(cache))
        data=detector.transcribe(media,language="ru",fp16=False,beam_size=5,
                                 condition_on_previous_text=False)
        text=str(data.get("text","")).strip()
        if not text:
            raise RuntimeError("OpenAI Whisper returned no audible Russian text")
        print("FALLBACK_ASR_USED",failure[:100],flush=True)
        return text,"OpenAI Whisper "+model+" CPU fallback"
    except Exception as exc:
        raise RuntimeError("BOTH_INDEPENDENT_ASR_ENGINES_FAILED: "+
            str(failure)[:130]+"; backup "+type(exc).__name__+": "+str(exc)[:130]) from exc
