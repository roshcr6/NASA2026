"""Preview router — FITS cutout → PNG."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from pydantic import BaseModel
from cache import get_preview, put_preview
from config import settings
from image_pipeline import generate_preview
from irsa_client import search_observations, get_cached_access_url
from validation import validate_coordinates, validate_size, sanitise_obs_id

router = APIRouter(tags=["preview"])
logger = logging.getLogger(__name__)

# Per-obs_id lock to prevent duplicate simultaneous downloads
_preview_locks: dict[str, asyncio.Lock] = {}


def _get_lock(key: str) -> asyncio.Lock:
    if key not in _preview_locks:
        _preview_locks[key] = asyncio.Lock()
    return _preview_locks[key]


class BatchPrefetchItem(BaseModel):
    obs_id: str
    ra: float
    dec: float
    size: float = 0.1
    collection: str = "spherex_qr3"


class BatchPrefetchRequest(BaseModel):
    items: list[BatchPrefetchItem]


@router.post(
    "/preview/batch-prefetch",
    summary="Concurrently prefetch and warm cache for multiple observations",
)
async def batch_prefetch(request: BatchPrefetchRequest):
    """
    Parallel background prefetcher. Uses bounded concurrency to download and
    warm the disk cache with PNG previews across worker threads.
    """
    semaphore = asyncio.Semaphore(settings.max_concurrent_requests)

    async def prefetch_one(item: BatchPrefetchItem) -> bool:
        cache_key = f"{item.obs_id}|{item.ra}|{item.dec}|{item.size}|{item.collection}"
        lock = _get_lock(cache_key)
        async with lock:
            cached = await get_preview(item.obs_id, item.ra, item.dec, item.size, item.collection)
            if cached:
                return True
            access_url = get_cached_access_url(item.obs_id, item.collection)
            if not access_url:
                records, _ = await search_observations(item.ra, item.dec, radius_deg=min(item.size * 2, 0.5))
                for r in records:
                    if r.obs_id == item.obs_id:
                        access_url = r.access_url
                        break
            if not access_url:
                return False
            async with semaphore:
                try:
                    async with httpx.AsyncClient(
                        headers={"User-Agent": "SPHEREx-SkyExplorer/1.0"},
                        follow_redirects=True,
                    ) as client:
                        png_bytes, meta = await generate_preview(
                            access_url=access_url,
                            ra=item.ra,
                            dec=item.dec,
                            size_deg=item.size,
                            obs_id=item.obs_id,
                            client=client,
                        )
                        meta["obs_id"] = item.obs_id
                        meta["collection"] = item.collection
                        await put_preview(item.obs_id, item.ra, item.dec, item.size, item.collection, png_bytes, meta)
                        return True
                except Exception as exc:
                    logger.warning("Prefetch failed for %s: %s", item.obs_id, exc)
                    return False

    tasks = [prefetch_one(item) for item in request.items[:12]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    success_count = sum(1 for r in results if r is True)
    return {"status": "ok", "total": len(request.items), "success": success_count}


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
    2. Fast lookup of access_url via in-memory index or SIA.
    3. Download FITS cutout from IRSA or S3 mirror.
    4. Offload CPU FITS stretch & PNG generation to thread pool.
    5. Cache and return image with provenance headers.
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

        # 1. Fast lookup from in-memory access map
        access_url = get_cached_access_url(obs_id, collection)

        # 2. If not found in RAM map, query SIA
        if not access_url:
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
            access_url = matching[0].access_url

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
