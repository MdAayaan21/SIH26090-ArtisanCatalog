"""
Member 4 — Sync Batch State Machine.

Lifecycle: queued -> processing -> awaiting_confirmation -> committed
(or -> failed at any point, with error_message set so the client can retry
or surface the error to the artisan via the readback flow).
"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import SyncBatch, SyncBatchStatus, Artisan
from ..schemas import SyncBatchCreate, SyncBatchOut, SyncBatchAdvance

logger = logging.getLogger("sync_router")
router = APIRouter(prefix="/sync", tags=["sync"])

# valid forward transitions — anything else is rejected to keep the batch
# lifecycle predictable for every module that reads SyncBatch.status
_ALLOWED_TRANSITIONS = {
    SyncBatchStatus.QUEUED: {SyncBatchStatus.PROCESSING, SyncBatchStatus.FAILED},
    SyncBatchStatus.PROCESSING: {SyncBatchStatus.AWAITING_CONFIRMATION, SyncBatchStatus.FAILED},
    SyncBatchStatus.AWAITING_CONFIRMATION: {SyncBatchStatus.COMMITTED, SyncBatchStatus.FAILED},
    SyncBatchStatus.COMMITTED: set(),
    SyncBatchStatus.FAILED: {SyncBatchStatus.QUEUED},  # allow artisan-triggered retry
}


@router.post("/create", response_model=SyncBatchOut)
def create_batch(payload: SyncBatchCreate, db: Session = Depends(get_db)):
    artisan = db.query(Artisan).filter(Artisan.id == payload.artisan_id).first()
    if artisan is None:
        raise HTTPException(404, "Artisan not found")

    existing = db.query(SyncBatch).filter(SyncBatch.client_batch_id == payload.client_batch_id).first()
    if existing:
        return existing  # idempotent create, handles duplicate offline-queue replays

    batch = SyncBatch(
        client_batch_id=payload.client_batch_id,
        artisan_id=payload.artisan_id,
        total_chunks_expected=payload.total_chunks_expected,
        status=SyncBatchStatus.QUEUED,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


@router.get("/{client_batch_id}", response_model=SyncBatchOut)
def get_batch(client_batch_id: str, db: Session = Depends(get_db)):
    batch = db.query(SyncBatch).filter(SyncBatch.client_batch_id == client_batch_id).first()
    if batch is None:
        raise HTTPException(404, "Batch not found")
    return batch


@router.post("/{client_batch_id}/advance", response_model=SyncBatchOut)
def advance_batch(client_batch_id: str, payload: SyncBatchAdvance, db: Session = Depends(get_db)):
    batch = db.query(SyncBatch).filter(SyncBatch.client_batch_id == client_batch_id).first()
    if batch is None:
        raise HTTPException(404, "Batch not found")

    try:
        next_status = SyncBatchStatus(payload.next_status)
    except ValueError:
        raise HTTPException(400, f"Invalid status '{payload.next_status}'")

    allowed = _ALLOWED_TRANSITIONS.get(batch.status, set())
    if next_status not in allowed:
        raise HTTPException(
            409,
            f"Cannot transition batch from '{batch.status.value}' to '{next_status.value}'. "
            f"Allowed next states: {[s.value for s in allowed]}",
        )

    batch.status = next_status
    batch.error_message = payload.error_message if next_status == SyncBatchStatus.FAILED else None
    db.commit()
    db.refresh(batch)
    logger.info("Batch %s advanced to %s", client_batch_id, next_status.value)
    return batch
