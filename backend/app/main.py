"""
Member 1 — Integration & Code Review: application entrypoint.

Wires every module's router into one FastAPI app, creates tables on first
run (swap for Alembic migrations in production), and enables CORS for the
mobile-web frontend.
"""
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from .config import settings
from .routers import artisans, upload, sync, pipeline, products, ondc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(
    title="AI-Driven Market Linkage & Smart Cataloging API",
    description="Voice-first, offline-tolerant catalog pipeline for marginalized artisans, exporting to ONDC.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to the deployed PWA origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(artisans.router)
app.include_router(upload.router)
app.include_router(sync.router)
app.include_router(pipeline.router)
app.include_router(products.router)
app.include_router(ondc.router)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    logger.info("Startup complete: tables ensured, media directories ready.")

os.makedirs(settings.media_root, exist_ok=True)
os.makedirs(settings.chunk_tmp_root, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.media_root), name="media")


@app.get("/health")
def health():
    return {"status": "ok"}