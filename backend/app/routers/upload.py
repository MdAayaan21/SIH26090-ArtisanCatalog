"""
Member 4 — Resumable Upload Endpoint.

Accepts media in small chunks so a capture can survive an interrupted 2G/3G
connection: the client resends only the chunks that never arrived, keyed by
(client_batch_id, file_id, chunk_index). Once all expected chunks for a file
are present they are concatenated into the final artifact under media_root.
"""
import os
import logging
from typing import Optional

import aiofiles
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import SyncBatch, SyncBatchStatus
from ..config import settings

logger = logging.getLogger("upload_router")
router = APIRouter(prefix="/upload", tags=["upload"])


def _chunk_dir_path(client_batch_id: str, file_id: str) -> str:
    return os.path.join(settings.chunk_tmp_root, client_batch_id, file_id)


def _chunk_dir(client_batch_id: str, file_id: str) -> str:
    path = _chunk_dir_path(client_batch_id, file_id)
    os.makedirs(path, exist_ok=True)
    return path


@router.post("/chunk")
async def upload_chunk(
    client_batch_id: str = Form(...),
    file_id: str = Form(...),          # stable id the client assigns per media file
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    media_type: str = Form(...),       # "photo" | "audio"
    chunk: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Accepts a single chunk. Idempotent: re-uploading the same
    (file_id, chunk_index) simply overwrites, so retries are always safe."""
    batch = db.query(SyncBatch).filter(SyncBatch.client_batch_id == client_batch_id).first()
    if batch is None:
        # First chunk of a brand-new batch auto-creates the SyncBatch row in
        # QUEUED state; artisan_id association happens via /sync/create beforehand
        # in the normal flow, but we guard here in case chunks race ahead.
        raise HTTPException(404, "Unknown client_batch_id — call /sync/create first")

    chunk_dir = _chunk_dir(client_batch_id, file_id)
    chunk_path = os.path.join(chunk_dir, f"{chunk_index:06d}.part")

    contents = await chunk.read()
    async with aiofiles.open(chunk_path, "wb") as f:
        await f.write(contents)

    received = len(os.listdir(chunk_dir))
    is_complete = received >= total_chunks

    final_path = None
    if is_complete:
        final_path = await _assemble_chunks(chunk_dir, client_batch_id, file_id, media_type, total_chunks)

    return {
        "file_id": file_id,
        "chunk_index": chunk_index,
        "received_chunks": received,
        "total_chunks": total_chunks,
        "complete": is_complete,
        "final_path": final_path,
    }


async def _assemble_chunks(chunk_dir: str, client_batch_id: str, file_id: str, media_type: str, total_chunks: int) -> str:
    ext = "webp" if media_type == "photo" else "wav"
    out_dir = os.path.join(settings.media_root, "raw", client_batch_id)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{file_id}.{ext}")

    async with aiofiles.open(out_path, "wb") as outfile:
        for i in range(total_chunks):
            part_path = os.path.join(chunk_dir, f"{i:06d}.part")
            if not os.path.exists(part_path):
                raise HTTPException(409, f"Missing chunk {i} — cannot assemble yet")
            async with aiofiles.open(part_path, "rb") as part:
                await outfile.write(await part.read())

    # cleanup temp chunks now the final file is written
    for i in range(total_chunks):
        part_path = os.path.join(chunk_dir, f"{i:06d}.part")
        if os.path.exists(part_path):
            os.remove(part_path)

    return out_path


@router.get("/status/{client_batch_id}/{file_id}")
def upload_status(client_batch_id: str, file_id: str):
    """Lets the client ask 'which chunks do you already have?' after
    reconnecting, so it only resends what's missing."""
    chunk_dir = _chunk_dir_path(client_batch_id, file_id)
    if not os.path.isdir(chunk_dir):
        return {"file_id": file_id, "received_chunk_indices": []}
    received = sorted(
        int(name.split(".")[0]) for name in os.listdir(chunk_dir) if name.endswith(".part")
    )
    return {"file_id": file_id, "received_chunk_indices": received}