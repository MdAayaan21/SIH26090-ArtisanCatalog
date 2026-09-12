"""
Member 5 — Structured Dialect Extraction.

Takes a raw regional-language transcript (e.g. "do kilo jaisa dhaaga laga,
teen ghante lage") and turns it into clean numeric/structured fields the
pricing engine and catalog can use, via a few-shot LLM prompt that teaches
the model to normalize colloquial units (kilos, "do ghante", "mutthi bhar",
etc.) into standard numbers.

Any field the transcript doesn't mention is left null so the pricing engine
knows to apply a CraftBenchmark fallback instead of guessing silently.
"""
import json
import logging
from typing import Optional

import httpx

from ..config import settings

logger = logging.getLogger("extraction_service")

SYSTEM_PROMPT = """You extract structured handicraft-listing data from a raw \
speech transcript in an Indian regional language or dialect. The speaker is \
an artisan describing something they made, often using colloquial units \
(e.g. "do kilo", "mutthi bhar", "teen ghante", "ek hafta"). Normalize all \
units to the numeric field's stated unit. If a field is not mentioned or \
cannot be confidently inferred, output null for it — never invent a value.

Respond with ONLY a JSON object, no prose, matching this exact shape:
{
  "title": string|null,            // short product name, in English, <=8 words
  "description": string|null,      // 1-2 sentence description, in English
  "category": string|null,         // one of: pottery, weaving, woodwork, jewelry,
                                    // basketry, metalwork, embroidery, painting, other
  "material_cost_inr": number|null,
  "labor_hours": number|null,
  "quantity_available": integer|null,
  "weight_kg": number|null,
  "length_cm": number|null,
  "width_cm": number|null,
  "height_cm": number|null
}"""

FEW_SHOT_EXAMPLES = [
    {
        "role": "user",
        "content": (
            "Transcript (Hindi, romanized): 'Yeh mitti ka diya hai, humne teen "
            "ghante lagaye banane mein, do kilo mitti lagi, ek dozen banaye hain'"
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "title": "Clay Diya (Oil Lamp)",
            "description": "Handmade terracotta oil lamp shaped from local clay.",
            "category": "pottery",
            "material_cost_inr": None,
            "labor_hours": 3,
            "quantity_available": 12,
            "weight_kg": 2,
            "length_cm": None,
            "width_cm": None,
            "height_cm": None,
        }),
    },
    {
        "role": "user",
        "content": (
            "Transcript (Tamil, romanized): 'Idhu kai naeasal thuni, moonu naal "
            "aachu seiyya, oru thuni thaan irukku'"
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "title": "Handwoven Cotton Cloth",
            "description": "Traditional handwoven cotton textile made over several days.",
            "category": "weaving",
            "material_cost_inr": None,
            "labor_hours": 72,
            "quantity_available": 1,
            "weight_kg": None,
            "length_cm": None,
            "width_cm": None,
            "height_cm": None,
        }),
    },
]


async def extract_structured_fields(transcript: str, source_language: str) -> dict:
    """Calls the Anthropic Messages API with a few-shot dialect-normalization
    prompt and returns a validated dict of structured listing fields."""
    if not settings.anthropic_api_key:
        logger.warning("No LLM key configured; returning empty extraction so "
                        "CraftBenchmark fallbacks apply to every field.")
        return _empty_fields()

    messages = FEW_SHOT_EXAMPLES + [
        {
            "role": "user",
            "content": f"Transcript (language={source_language}): '{transcript}'",
        }
    ]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.extraction_model,
                    "max_tokens": 500,
                    "system": SYSTEM_PROMPT,
                    "messages": messages,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            raw_text = "".join(
                block["text"] for block in data.get("content", []) if block.get("type") == "text"
            )
            return _parse_and_validate(raw_text)
    except Exception as exc:
        logger.error("LLM extraction failed, falling back to empty fields: %s", exc)
        return _empty_fields()


def _parse_and_validate(raw_text: str) -> dict:
    cleaned = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.error("LLM did not return valid JSON: %r", raw_text)
        return _empty_fields()

    defaults = _empty_fields()
    defaults.update({k: v for k, v in parsed.items() if k in defaults})
    return defaults


def _empty_fields() -> dict:
    return {
        "title": None,
        "description": None,
        "category": None,
        "material_cost_inr": None,
        "labor_hours": None,
        "quantity_available": None,
        "weight_kg": None,
        "length_cm": None,
        "width_cm": None,
        "height_cm": None,
    }
