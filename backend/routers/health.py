"""Health and readiness endpoints."""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter

from cache import cache_entry_count
from config import settings
from models import HealthResponse

router = APIRouter(tags=["ops"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse, summary="Service health check")
async def health_check():
    """Returns service status and IRSA reachability."""
    irsa_ok = False
    try:
        async with httpx.AsyncClient() as client:
            r = await client.head(settings.irsa_sia_url, timeout=5.0)
            irsa_ok = r.status_code < 500
    except Exception:
        pass

    return HealthResponse(
        status="ok" if irsa_ok else "degraded",
        irsa_reachable=irsa_ok,
        cache_entries=cache_entry_count(),
    )
