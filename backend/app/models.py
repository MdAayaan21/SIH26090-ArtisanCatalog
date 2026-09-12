"""
Canonical data schema shared by the whole team (owned/guarded by Member 1).
Every module MUST import these models rather than redefining fields, so
database records stay consistent across the AI, pricing, and sync pipelines.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Float, Integer, Boolean, DateTime, ForeignKey,
    Enum, Text, JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from .database import Base


def gen_uuid():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SyncBatchStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMMITTED = "committed"
    FAILED = "failed"


class ProductStatus(str, enum.Enum):
    DRAFT = "draft"                # created from raw voice+photo, not yet enriched
    ENRICHED = "enriched"          # ASR + extraction + vision done
    PRICED = "priced"              # pricing engine has run
    CONFIRMED = "confirmed"        # artisan confirmed via readback card
    EXPORTED = "exported"          # pushed to ONDC catalog


# ---------------------------------------------------------------------------
# Artisan
# ---------------------------------------------------------------------------

class Artisan(Base):
    __tablename__ = "artisans"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    full_name = Column(String(120), nullable=False)
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    preferred_language = Column(String(10), nullable=False, default="hi")  # ISO code, Bhashini lang id
    village = Column(String(120))
    district = Column(String(120))
    state = Column(String(120))
    craft_category = Column(String(80))          # links to CraftBenchmark.category
    ondc_seller_id = Column(String(120))          # assigned once onboarded to ONDC
    created_at = Column(DateTime, default=datetime.utcnow)

    products = relationship("Product", back_populates="artisan")
    sync_batches = relationship("SyncBatch", back_populates="artisan")


# ---------------------------------------------------------------------------
# CraftBenchmark (fallback defaults, Member 6)
# ---------------------------------------------------------------------------

class CraftBenchmark(Base):
    __tablename__ = "craft_benchmarks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(80), unique=True, nullable=False, index=True)
    default_labor_hours = Column(Float, nullable=False)
    default_material_cost = Column(Float, nullable=False)       # INR
    default_wage_benchmark = Column(Float, nullable=False)      # INR/hour
    default_length_cm = Column(Float, nullable=True)
    default_width_cm = Column(Float, nullable=True)
    default_height_cm = Column(Float, nullable=True)
    default_weight_kg = Column(Float, nullable=True)
    market_adjustment_pct = Column(Float, nullable=False, default=0.15)


# ---------------------------------------------------------------------------
# SyncBatch — one offline "session" of captures uploaded together
# ---------------------------------------------------------------------------

class SyncBatch(Base):
    __tablename__ = "sync_batches"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    client_batch_id = Column(String(64), unique=True, nullable=False, index=True)  # from IndexedDB
    artisan_id = Column(UUID(as_uuid=False), ForeignKey("artisans.id"), nullable=False)
    status = Column(Enum(SyncBatchStatus), nullable=False, default=SyncBatchStatus.QUEUED)
    total_chunks_expected = Column(Integer, default=0)
    chunks_received = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    artisan = relationship("Artisan", back_populates="sync_batches")
    products = relationship("Product", back_populates="sync_batch")


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------

class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    artisan_id = Column(UUID(as_uuid=False), ForeignKey("artisans.id"), nullable=False)
    sync_batch_id = Column(UUID(as_uuid=False), ForeignKey("sync_batches.id"), nullable=True)

    status = Column(Enum(ProductStatus), nullable=False, default=ProductStatus.DRAFT)

    # raw captured media (server-side paths, populated by upload endpoint)
    raw_audio_path = Column(String(255), nullable=True)
    raw_photo_paths = Column(JSON, default=list)          # list[str]
    processed_photo_paths = Column(JSON, default=list)    # list[str], bg-removed

    # ASR + extraction output (Member 5)
    transcript_raw = Column(Text, nullable=True)
    transcript_language = Column(String(10), nullable=True)
    asr_engine_used = Column(String(20), nullable=True)    # "bhashini" | "whisper_fallback"
    extracted_fields = Column(JSON, default=dict)          # structured dialect-normalized fields

    # canonical structured listing fields
    title = Column(String(150), nullable=True)
    description = Column(Text, nullable=True)
    category = Column(String(80), nullable=True)
    material_cost = Column(Float, nullable=True)
    labor_hours = Column(Float, nullable=True)
    quantity_available = Column(Integer, default=1)
    weight_kg = Column(Float, nullable=True)
    length_cm = Column(Float, nullable=True)
    width_cm = Column(Float, nullable=True)
    height_cm = Column(Float, nullable=True)

    # pricing output (Member 6)
    suggested_price = Column(Float, nullable=True)
    price_breakdown = Column(JSON, nullable=True)  # {material, labor, market_adjustment}
    used_benchmark_fallback = Column(Boolean, default=False)

    # confirmation / readback (Member 2 <-> Member 4)
    tts_readback_audio_path = Column(String(255), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)

    # ONDC export (Member 6)
    ondc_catalog_json = Column(JSON, nullable=True)
    exported_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    artisan = relationship("Artisan", back_populates="products")
    sync_batch = relationship("SyncBatch", back_populates="products")
