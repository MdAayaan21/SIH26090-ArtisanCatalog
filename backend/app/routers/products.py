"""
Product endpoints: creation from an assembled SyncBatch, listing, and the
tap-to-confirm action the readback card (Member 2) calls once the artisan
has heard the TTS summary and taps "Confirm".
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product, ProductStatus, SyncBatch
from ..schemas import ProductOut, ProductConfirm

router = APIRouter(prefix="/products", tags=["products"])


@router.post("/from-batch/{client_batch_id}", response_model=ProductOut)
def create_product_from_batch(
    client_batch_id: str,
    audio_file_id: str,
    photo_file_ids: list[str],
    db: Session = Depends(get_db),
):
    """Called once all chunks for a capture session have been assembled
    (routers/upload.py). Builds the raw Product row that /pipeline/run
    will then enrich."""
    import os
    from ..config import settings

    batch = db.query(SyncBatch).filter(SyncBatch.client_batch_id == client_batch_id).first()
    if batch is None:
        raise HTTPException(404, "Batch not found")

    raw_dir = os.path.join(settings.media_root, "raw", client_batch_id)
    audio_path = os.path.join(raw_dir, f"{audio_file_id}.wav")
    photo_paths = [os.path.join(raw_dir, f"{fid}.webp") for fid in photo_file_ids]

    product = Product(
        artisan_id=batch.artisan_id,
        sync_batch_id=batch.id,
        raw_audio_path=audio_path,
        raw_photo_paths=photo_paths,
        status=ProductStatus.DRAFT,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(404, "Product not found")
    return product


@router.get("/artisan/{artisan_id}", response_model=list[ProductOut])
def list_products_for_artisan(artisan_id: str, db: Session = Depends(get_db)):
    return db.query(Product).filter(Product.artisan_id == artisan_id).all()


@router.post("/{product_id}/confirm", response_model=ProductOut)
def confirm_product(product_id: str, payload: ProductConfirm, db: Session = Depends(get_db)):
    """Tap-to-confirm from the readback overlay card. The artisan can accept
    the AI-suggested price/title as-is or override it before confirming."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(404, "Product not found")
    if product.status != ProductStatus.PRICED:
        raise HTTPException(409, f"Product must be PRICED before it can be confirmed (currently {product.status.value})")

    if not payload.confirmed:
        # artisan rejected the listing on readback — leave it PRICED so they
        # can re-record or edit rather than silently discarding their work
        return product

    if payload.title_override:
        product.title = payload.title_override
    if payload.price_override is not None:
        product.suggested_price = payload.price_override
    if payload.quantity_available is not None:
        product.quantity_available = payload.quantity_available

    product.status = ProductStatus.CONFIRMED
    product.confirmed_at = datetime.utcnow()

    if product.sync_batch:
        from ..models import SyncBatchStatus
        product.sync_batch.status = SyncBatchStatus.COMMITTED

    db.commit()
    db.refresh(product)
    return product
