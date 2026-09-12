"""
Member 5 — AI & Speech Specialist.

Speech-to-text pipeline:
  1. Try Bhashini ULCA ASR (best accuracy for Indian regional languages/dialects).
  2. On any server/network error, automatically fall back to OpenAI Whisper.

Both paths return a normalized dict so the rest of the pipeline never has to
know which engine actually ran.
"""
import base64
import logging
from typing import Optional

import httpx
from openai import OpenAI
from fastapi.concurrency import run_in_threadpool

from ..config import settings

logger = logging.getLogger("asr_service")

# Bhashini language-code -> ISO-ish tag used across the app
BHASHINI_LANG_MAP = {
    "hi": "hi", "mr": "mr", "ta": "ta", "te": "te", "kn": "kn",
    "bn": "bn", "gu": "gu", "pa": "pa", "or": "or", "ml": "ml",
    "as": "as", "en": "en",
}


class ASRResult:
    def __init__(self, transcript: str, language: str, engine: str):
        self.transcript = transcript
        self.language = language
        self.engine = engine  # "bhashini" | "whisper_fallback"

    def to_dict(self):
        return {"transcript": self.transcript, "language": self.language, "engine": self.engine}


async def _transcribe_with_bhashini(audio_bytes: bytes, language: str) -> Optional[ASRResult]:
    """Calls the Bhashini ULCA /compute pipeline for ASR. Returns None on failure
    so the caller can trigger the Whisper fallback rather than raising."""
    if not settings.bhashini_inference_key or not settings.bhashini_pipeline_id:
        logger.warning("Bhashini not configured; skipping to fallback")
        return None

    lang_code = BHASHINI_LANG_MAP.get(language, "hi")
    payload = {
        "pipelineTasks": [
            {
                "taskType": "asr",
                "config": {
                    "language": {"sourceLanguage": lang_code},
                    "serviceId": "",  # resolved by pipelineId at compute time
                    "audioFormat": "wav",
                    "samplingRate": 16000,
                },
            }
        ],
        "inputData": {
            "audio": [{"audioContent": base64.b64encode(audio_bytes).decode("utf-8")}]
        },
        "pipelineId": settings.bhashini_pipeline_id,
    }
    headers = {
        "Authorization": settings.bhashini_inference_key,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(settings.bhashini_api_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            transcript = (
                data["pipelineResponse"][0]["output"][0]["source"]
                if data.get("pipelineResponse")
                else None
            )
            if not transcript:
                return None
            return ASRResult(transcript=transcript, language=lang_code, engine="bhashini")
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        logger.warning("Bhashini ASR failed, will fall back to Whisper: %s", exc)
        return None


def _transcribe_with_whisper(audio_bytes: bytes, filename: str, language: str) -> ASRResult:
    """Synchronous fallback via OpenAI Whisper. Kept sync since the openai SDK's
    sync client is simplest to reason about for a fallback path."""
    client = OpenAI(api_key=settings.openai_api_key)
    # Whisper needs a file-like object with a name attribute for format sniffing
    import io
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename or "audio.wav"

    transcription = client.audio.transcriptions.create(
        model=settings.whisper_model,
        file=audio_file,
        language=language if language in BHASHINI_LANG_MAP else None,
    )
    return ASRResult(transcript=transcription.text, language=language, engine="whisper_fallback")


async def transcribe_audio(audio_bytes: bytes, filename: str, language: str = "hi") -> dict:
    """Public entry point used by the pipeline router. Always returns a dict,
    never raises for expected engine failures (Bhashini down, etc.) — only
    raises if BOTH engines fail, since that means the batch truly cannot proceed."""
    result = await _transcribe_with_bhashini(audio_bytes, language)
    if result is not None:
        return result.to_dict()

    try:
        result = await run_in_threadpool(_transcribe_with_whisper, audio_bytes, filename, language)
        return result.to_dict()
    except Exception as exc:
        logger.error("Both Bhashini and Whisper failed: %s", exc)
        raise RuntimeError("Speech recognition unavailable — both primary and fallback ASR failed") from exc