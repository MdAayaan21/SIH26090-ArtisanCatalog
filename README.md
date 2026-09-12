# Kaarigar Bazaar — AI-Driven Market Linkage & Smart Cataloging

Voice-first, offline-tolerant catalog pipeline that turns an artisan's spoken
description and smartphone photos into a priced, ONDC-exportable e-commerce
listing — no typing required.

## Layout

```
artisan-app/
├── backend/                     Member 1 / Member 4 / Member 5 / Member 6
│   ├── app/
│   │   ├── main.py               FastAPI entrypoint, wires every router
│   │   ├── config.py             Env-driven settings (Bhashini/Whisper/LLM/ONDC keys)
│   │   ├── database.py           SQLAlchemy engine + session (pooled)
│   │   ├── models.py             Shared schema: Artisan, Product, SyncBatch, CraftBenchmark
│   │   ├── schemas.py            Pydantic request/response models
│   │   ├── seed_benchmarks.py    Seeds CraftBenchmark fallback defaults
│   │   ├── routers/
│   │   │   ├── artisans.py       Artisan onboarding/CRUD
│   │   │   ├── upload.py         Member 4 — resumable chunked media upload
│   │   │   ├── sync.py           Member 4 — SyncBatch state machine
│   │   │   ├── pipeline.py       Member 1 — glue: ASR -> extraction -> vision -> pricing
│   │   │   ├── products.py       Product creation + readback tap-to-confirm
│   │   │   └── ondc.py           Member 6 — Beckn/ONDC catalog export
│   │   └── services/
│   │       ├── asr_service.py         Member 5 — Bhashini ASR + Whisper fallback
│   │       ├── extraction_service.py  Member 5 — few-shot dialect -> structured fields
│   │       ├── vision_service.py      Member 5 — rembg background removal
│   │       ├── pricing_service.py     Member 6 — cost-plus formula + benchmark fallback
│   │       └── ondc_service.py        Member 6 — Beckn JSON serializer
│   ├── requirements.txt
│   └── .env.example
└── frontend/                    Member 2 / Member 3
    ├── index.html                Camera -> mic -> processing -> readback -> done screens
    ├── styles.css                Voice-first, high-contrast, large-touch-target design
    ├── app.js                    Member 2 — camera capture, mic recording, readback TTS
    ├── db.js                     Member 3 — IndexedDB atomic draft persistence
    ├── compress.js               Member 3 — client-side WebP compression (<300KB)
    ├── sync-daemon.js            Member 3 — online/visibilitychange auto-sync
    ├── sw.js                     App-shell service worker (offline load)
    └── manifest.json             PWA manifest
```

## Running the backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in Bhashini / OpenAI / Anthropic / DB credentials
# create a Postgres database matching DATABASE_URL, then:
python -m app.seed_benchmarks
uvicorn app.main:app --reload --port 8000
```

The API is now live at `http://localhost:8000` (interactive docs at `/docs`).

## Running the frontend

The frontend is a dependency-free PWA (no build step). Serve it with any
static file server so `getUserMedia` and the service worker are happy:

```bash
cd frontend
python3 -m http.server 5500
```

Open `http://localhost:5500` on a phone (or desktop with a webcam/mic) and
set `window.KAARIGAR_API_BASE` in the browser console, or edit the constant
at the top of `app.js`, if your backend isn't on `localhost:8000`.

## End-to-end flow

1. **Camera** — artisan snaps 1+ photos of the product (Member 2 UI,
   Member 3 compresses each to WebP <300KB before it ever touches storage).
2. **Voice** — artisan taps the large mic button and describes the item in
   their own language/dialect.
3. **Submit** — both media are written to IndexedDB in one atomic
   transaction (Member 3), and the UI moves to a processing screen while the
   sync daemon uploads chunks as connectivity allows (Member 3 <-> Member 4).
4. **Pipeline** — once the backend has all chunks, `/pipeline/run/{id}`
   (Member 1's glue code) sequentially runs Bhashini/Whisper ASR, LLM
   dialect-normalized extraction, rembg background removal, and the
   cost-plus pricing formula (Member 5, Member 6).
5. **Readback** — the artisan hears a TTS summary of the listing and price,
   and taps to confirm or re-record (Member 2).
6. **Export** — a confirmed product can be pushed to ONDC via
   `/ondc/export/{product_id}`, producing a Beckn-compliant catalog fragment
   (Member 6).

## Team workflow reminders

- Protected `main`; every task starts on `feat/<module-name>` from an
  up-to-date `main`.
- Open a PR when a module is ready; Member 1 reviews architecture integrity,
  confirms the shared `Artisan` / `Product` / `SyncBatch` schemas weren't
  diverged from, and merges.
