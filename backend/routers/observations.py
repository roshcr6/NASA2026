"""Observations router — timeline and observation search."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query
from cachetools import TTLCache

from config import settings
from irsa_client import search_observations
from models import TimelineResponse
from validation import validate_coordinates, validate_radius

router = APIRouter(tags=["observations"])
logger = logging.getLogger(__name__)

# In-process metadata cache (TTL-based, thread-safe enough for single process)
_meta_cache: TTLCache = TTLCache(maxsize=256, ttl=settings.metadata_cache_ttl)


@router.get("/observations", response_model=TimelineResponse, summary="Search SPHEREx observations")
async def get_observations(
    ra: float = Query(..., description="Right ascension (degrees, ICRS, [0,360))"),
    dec: float = Query(..., description="Declination (degrees, ICRS, [-90,90])"),
    radius: float = Query(0.15, description="Search radius (degrees, max 0.5)"),
):
    """
    Return all SPHEREx Level-2 Spectral Images overlapping a circular sky region.

    Queries QR3 and QR2 in parallel. Results are sorted newest-first.
    Actual archive data only — no fabricated epochs.
    """
    validate_coordinates(ra, dec)
    validate_radius(radius)

    cache_key = f"obs|{ra:.5f}|{dec:.5f}|{radius:.5f}"
    if cache_key in _meta_cache:
        logger.info("Metadata cache hit: %s", cache_key)
        return _meta_cache[cache_key]

    records, warnings = await search_observations(ra, dec, radius_deg=radius)

    response = TimelineResponse(
        ra=ra,
        dec=dec,
        radius_deg=radius,
        observations=records,
        releases_queried=[settings.preferred_release, settings.fallback_release],
        total=len(records),
        warnings=warnings,
    )
    _meta_cache[cache_key] = response
    return response


@router.get("/timeline", response_model=TimelineResponse, summary="Observation timeline for a position")
async def get_timeline(
    ra: float = Query(...),
    dec: float = Query(...),
):
    """Alias for /observations with default radius, sorted by time."""
    return await get_observations(ra=ra, dec=dec, radius=0.15)
