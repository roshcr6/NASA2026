"""
SPHEREx Sky Explorer — FastAPI Backend
Entry point: mounts all routers, configures CORS, initialises shared state.
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from routers import observations, preview, compare, health

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("SPHEREx backend starting (release preference: %s)", settings.preferred_release)
    yield
    logger.info("SPHEREx backend shutting down")


app = FastAPI(
    title="SPHEREx Sky Explorer API",
    description=(
        "Backend for SPHEREx Sky Explorer — 2026 NASA Space Apps Challenge.\n\n"
        "Queries real SPHEREx data from the IRSA archive (QR2/QR3) and serves\n"
        "image previews, observation timelines and comparison metadata."
    ),
    version="1.0.0",
    lifespan=lifespan,
    # Never expose internal detail in public error bodies
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
)

# ── CORS ────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Accept", "Cache-Control"],
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(observations.router, prefix="/api")
app.include_router(preview.router,      prefix="/api")
app.include_router(compare.router,      prefix="/api")


# ── Global exception handler ─────────────────────────────────────────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.exception("Unhandled exception on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "message": "An unexpected error occurred."},
    )
