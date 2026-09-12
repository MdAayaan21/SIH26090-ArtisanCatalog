"""
Pydantic schemas for request/response validation. Kept in lockstep with
app.models by Member 1 during PR review.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Artisan
# ---------------------------------------------------------------------------

class ArtisanCreate(BaseModel):
    full_name: str
    phone_number: str
    preferred_language: str = "hi"
    village: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    craft_category: Optional[str] = None


class ArtisanOut(ArtisanCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    ondc_seller_id: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Sync batch lifecycle
# ---------------------------------------------------------------------------

class SyncBatchCreate(BaseModel):
    client_batch_id: str
    artisan_id: str
    total_chunks_expected: int


class SyncBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    client_batch_id: str
    status: str
    chunks_received: int
    total_chunks_expected: int
    error_message: Optional[str] = None
    updated_at: datetime


class SyncBatchAdvance(BaseModel):
    """Body used to move a batch to the next state machine step."""
    next_status: str  # one of SyncBatchStatus values
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------

class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    artisan_id: str
    status: str
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    transcript_raw: Optional[str] = None
    extracted_fields: Optional[Dict[str, Any]] = None
    material_cost: Optional[float] = None
    labor_hours: Optional[float] = None
    suggested_price: Optional[float] = None
    price_breakdown: Optional[Dict[str, Any]] = None
    used_benchmark_fallback: Optional[bool] = None
    processed_photo_paths: Optional[List[str]] = None
    tts_readback_audio_path: Optional[str] = None
    ondc_catalog_json: Optional[Dict[str, Any]] = None
    updated_at: datetime


class ProductConfirm(BaseModel):
    """Artisan tap-to-confirm on the readback card — optional field overrides."""
    confirmed: bool
    title_override: Optional[str] = None
    price_override: Optional[float] = None
    quantity_available: Optional[int] = None


class PipelineRunResult(BaseModel):
    product_id: str
    status: str
    transcript: Optional[str] = None
    extracted_fields: Optional[Dict[str, Any]] = None
    suggested_price: Optional[float] = None
    readback_text: Optional[str] = None
