"""
Member 1 — Integration & Code Review: pipeline glue code.

This is the "connect the pieces" module: once a SyncBatch has all its raw
media assembled (see routers/upload.py), this endpoint drives the product
through every downstream module in sequence:

    raw audio + photos
        -> ASR (Member 5)
        -> structured dialect extraction (Member 5)
        -> background removal (Member 5)
        -> cost-plus pricing with benchmark fallback (Member 6)
        -> readback text assembly (for Member 2's TTS confirmation card)

Each step is wrapped so a failure in one module marks the SyncBatch FAILED
with a clear error_message instead of leaving the pipeline half-run.
"""
import logging
import os
from typing import List

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product, ProductStatus, SyncBatch, SyncBatchStatus, Artisan
from ..schemas import PipelineRunResult
from ..services import asr_service, extraction_service, vision_service, pricing_service
from ..config import settings

logger = logging.getLogger("pipeline_router")
router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/run/{product_id}", response_model=PipelineRunResult)
async def run_pipeline(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(404, "Product not found")

    batch = product.sync_batch
    artisan = db.query(Artisan).filter(Artisan.id == product.artisan_id).first()

    if batch:
        batch.status = SyncBatchStatus.PROCESSING
        db.commit()

    try:
        transcript_text = await _run_asr_step(product, artisan, db)
        extracted = await _run_extraction_step(product, transcript_text, artisan, db)
        _run_vision_step(product, db)
        price_result = _run_pricing_step(product, db)
        readback_text = _build_readback_text(product, price_result)

        product.status = ProductStatus.PRICED
        db.commit()

        if batch:
            batch.status = SyncBatchStatus.AWAITING_CONFIRMATION
            db.commit()

        return PipelineRunResult(
            product_id=product.id,
            status=product.status.value,
            transcript=transcript_text,
            extracted_fields=extracted,
            suggested_price=product.suggested_price,
            readback_text=readback_text,
        )

    except Exception as exc:
        logger.exception("Pipeline failed for product %s", product_id)
        if batch:
            batch.status = SyncBatchStatus.FAILED
            batch.error_message = str(exc)
            db.commit()
        raise HTTPException(500, f"Pipeline failed at product {product_id}: {exc}")


async def _run_asr_step(product: Product, artisan: Artisan, db: Session) -> str:
    if not product.raw_audio_path or not os.path.exists(product.raw_audio_path):
        raise RuntimeError("No raw audio found for product — cannot run ASR step")

    with open(product.raw_audio_path, "rb") as f:
        audio_bytes = f.read()

    result = await asr_service.transcribe_audio(
        audio_bytes=audio_bytes,
        filename=os.path.basename(product.raw_audio_path),
        language=artisan.preferred_language,
    )
    product.transcript_raw = result["transcript"]
    product.transcript_language = result["language"]
    product.asr_engine_used = result["engine"]
    db.commit()
    return result["transcript"]


async def _run_extraction_step(product: Product, transcript: str, artisan: Artisan, db: Session) -> dict:
    extracted = await extraction_service.extract_structured_fields(
        transcript=transcript, source_language=artisan.preferred_language
    )
    product.extracted_fields = extracted

    # copy extracted fields onto the canonical Product columns; anything null
    # here is intentionally left null so pricing_service applies benchmarks
    product.title = extracted.get("title")
    product.description = extracted.get("description")
    product.category = extracted.get("category") or artisan.craft_category
    product.material_cost = extracted.get("material_cost_inr")
    product.labor_hours = extracted.get("labor_hours")
    product.quantity_available = extracted.get("quantity_available") or 1
    product.weight_kg = extracted.get("weight_kg")
    product.length_cm = extracted.get("length_cm")
    product.width_cm = extracted.get("width_cm")
    product.height_cm = extracted.get("height_cm")

    product.status = ProductStatus.ENRICHED
    db.commit()
    return extracted


def _run_vision_step(product: Product, db: Session) -> List[str]:
    raw_paths = product.raw_photo_paths or []
    if not raw_paths:
        logger.warning("Product %s has no raw photos to process", product.id)
        return []

    processed = vision_service.process_product_photos(raw_paths, product.id, settings.media_root)
    product.processed_photo_paths = processed
    db.commit()
    return processed


def _run_pricing_step(product: Product, db: Session):
    price_result = pricing_service.calculate_price(
        db=db,
        category=product.category,
        material_cost=product.material_cost,
        labor_hours=product.labor_hours,
    )
    dims = pricing_service.fill_dimension_fallbacks(
        db, product.category, product.weight_kg, product.length_cm, product.width_cm, product.height_cm
    )

    product.material_cost = price_result.material_cost
    product.labor_hours = price_result.labor_hours
    product.suggested_price = price_result.suggested_price
    product.price_breakdown = price_result.breakdown()
    product.used_benchmark_fallback = price_result.used_benchmark_fallback
    product.weight_kg = dims["weight_kg"]
    product.length_cm = dims["length_cm"]
    product.width_cm = dims["width_cm"]
    product.height_cm = dims["height_cm"]
    db.commit()
    return price_result


def _build_readback_text(product: Product, price_result) -> str:
    """Plain-language summary handed to Member 2's TTS readback card so the
    artisan can hear their listing confirmed before it goes live."""
    fallback_note = " Kuch details anumaanit hain (some details were estimated)." \
        if price_result.used_benchmark_fallback else ""
    return (
        f"{product.title or 'Aapka utpaad'}. "
        f"Suggested price: {price_result.suggested_price:.0f} rupees. "
        f"{product.description or ''}{fallback_note} "
        f"Confirm karne ke liye tap karein."
    )
