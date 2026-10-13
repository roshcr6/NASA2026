"""Preview router — FITS cutout → PNG."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from cache import get_preview, put_preview
from config import settings
from image_pipeline import generate_preview
from irsa_client import search_observations
from validation import validate_coordinates, validate_size, sanitise_obs_id

router = APIRouter(tags=["preview"])
logger = logging.getLogger(__name__)

# Per-obs_id lock to prevent duplicate simultaneous downloads
_preview_locks: dict[str, asyncio.Lock] = {}


def _get_lock(key: str) -> asyncio.Lock:
    if key not in _preview_locks:
        _preview_locks[key] = asyncio.Lock()
    return _preview_locks[key]


@router.get(
    "/preview/{obs_id}",
    summary="Retrieve a PNG preview for one SPHEREx observation",
    response_class=Response,
    responses={
        200: {"content": {"image/png": {}}},
        404: {"description": "Observation not found"},
        422: {"description": "Invalid parameters"},
        502: {"description": "IRSA upstream error"},
    },
)
async def get_preview_image(
    obs_id: str,
    ra: float = Query(..., description="Centre RA (degrees)"),
    dec: float = Query(..., description="Centre Dec (degrees)"),
    collection: str = Query("spherex_qr3", description="IRSA collection name"),
    size: float = Query(0.1, description="Cutout side length (degrees, max 0.5)"),
):
    """
    Serve a PNG preview for one SPHEREx observation.

    1. Check disk cache.
    2. Look up access_url via SIA (validates obs_id belongs to an allowed dataset).
    3. Download FITS cutout from IRSA.
    4. Process and cache PNG.
    5. Return image with provenance headers.

    The obs_id is validated against the live archive — arbitrary URLs cannot
    be fetched via this endpoint (SSRF prevention).
    """
    validate_coordinates(ra, dec)
    validate_size(size)
    obs_id = sanitise_obs_id(obs_id)

    cache_key = f"{obs_id}|{ra}|{dec}|{size}|{collection}"
    lock = _get_lock(cache_key)

    async with lock:
        # Cache check
        cached = await get_preview(obs_id, ra, dec, size, collection)
        if cached:
            png_bytes, meta = cached
            logger.info("Preview cache hit: %s", obs_id)
            return _build_response(png_bytes, meta, obs_id, ra, dec, collection)

        # Validate that obs_id actually belongs to this collection
        records, _ = await search_observations(ra, dec, radius_deg=min(size * 2, 0.5))
        matching = [r for r in records if r.obs_id == obs_id and r.collection == collection]

        if not matching:
            # Wider search fallback
            records, _ = await search_observations(ra, dec, radius_deg=0.3)
            matching = [r for r in records if r.obs_id == obs_id]

        if not matching:
            raise HTTPException(
                status_code=404,
                detail=f"Observation {obs_id!r} not found in SPHEREx archive for this position.",
            )

        record = matching[0]
        access_url = record.access_url

        # Download + process
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": "SPHEREx-SkyExplorer/1.0"},
                follow_redirects=True,
            ) as client:
                png_bytes, meta = await generate_preview(
                    access_url=access_url,
                    ra=ra,
                    dec=dec,
                    size_deg=size,
                    obs_id=obs_id,
                    client=client,
                )
        except ValueError as exc:
            logger.warning("Preview generation failed for %s: %s", obs_id, exc)
            raise HTTPException(status_code=502, detail=f"Could not generate preview: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            logger.warning("IRSA HTTP error for %s: %s", obs_id, exc)
            raise HTTPException(status_code=502, detail="IRSA returned an error.") from exc
        except Exception as exc:
            logger.error("Unexpected preview error for %s: %s", obs_id, exc)
            raise HTTPException(status_code=502, detail="Preview generation failed.") from exc

        # Add provenance to meta
        meta["obs_id"] = obs_id
        meta["collection"] = collection
        meta["access_url_domain"] = "irsa.ipac.caltech.edu"

        await put_preview(obs_id, ra, dec, size, collection, png_bytes, meta)
        return _build_response(png_bytes, meta, obs_id, ra, dec, collection)


def _build_response(png_bytes, meta, obs_id, ra, dec, collection) -> Response:
    headers = {
        "Cache-Control": "public, max-age=86400",
        "X-SPHEREx-Obs-Id": obs_id,
        "X-SPHEREx-Collection": collection,
        "X-SPHEREx-RA": str(ra),
        "X-SPHEREx-Dec": str(dec),
        "X-Data-Attribution": "SPHEREx/IRSA/IPAC/JPL/Caltech/NASA",
    }
    if meta.get("wavelength_um"):
        headers["X-SPHEREx-Wavelength-Um"] = str(meta["wavelength_um"])
    return Response(content=png_bytes, media_type="image/png", headers=headers)
