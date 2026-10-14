"""
IRSA SIA v2 adapter — metadata discovery only.

Architecture:
  • Query SIA v2 with COLLECTION=spherex_qr3 (preferred), then QR2 as fallback.
  • Parse the JSON response into ObservationRecord objects.
  • Bounded concurrency via asyncio.Semaphore.
  • Retries on transient HTTP errors with exponential back-off + jitter.
  • Results are NOT downloaded here — only metadata URLs are returned.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx

from config import settings
from models import ObservationRecord

logger = logging.getLogger(__name__)

# Global semaphore — limits total parallel IRSA requests across all users
_sem = asyncio.Semaphore(settings.max_concurrent_requests)

# In-memory fast cache mapping (obs_id, collection) -> access_url
_OBS_ACCESS_MAP: dict[tuple[str, str], str] = {}


def get_cached_access_url(obs_id: str, collection: str) -> Optional[str]:
    """Retrieve fast in-memory access URL discovered during recent SIA searches."""
    return _OBS_ACCESS_MAP.get((obs_id, collection))


def cache_access_url(obs_id: str, collection: str, access_url: str) -> None:
    """Store fast mapping for observation access URL."""
    if len(_OBS_ACCESS_MAP) > 4000:
        _OBS_ACCESS_MAP.clear()
    _OBS_ACCESS_MAP[(obs_id, collection)] = access_url


# ── Internal helpers ──────────────────────────────────────────────────────────


def _mjd_to_utc(mjd: float) -> Optional[datetime]:
    """Convert Modified Julian Date to UTC datetime."""
    try:
        # MJD epoch: 1858-11-17 00:00:00 UTC; JD–MJD offset = 2400000.5
        jd = mjd + 2400000.5
        # Unix epoch: JD 2440587.5
        unix = (jd - 2440587.5) * 86400.0
        return datetime.fromtimestamp(unix, tz=timezone.utc)
    except Exception:
        return None


def _safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        return None if (f != f) else f  # NaN guard
    except (TypeError, ValueError):
        return None


def _safe_int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _parse_row(row: dict, collection: str) -> Optional[ObservationRecord]:
    """Map one SIA JSON result row → ObservationRecord. Returns None on parse failure."""
    try:
        access_url = row.get("access_url") or row.get("access_estsize") or ""
        # SIA JSON uses 'access_url' as the key
        if not access_url:
            return None

        obs_id = str(row.get("obs_id") or row.get("obs_publisher_did") or access_url)
        cache_access_url(obs_id, collection, access_url)
        mjd_start = _safe_float(row.get("t_min"))
        mjd_stop  = _safe_float(row.get("t_max"))
        em_min    = _safe_float(row.get("em_min"))
        em_max    = _safe_float(row.get("em_max"))

        return ObservationRecord(
            obs_id=obs_id,
            collection=collection,
            access_url=access_url,
            obs_start=_mjd_to_utc(mjd_start) if mjd_start else None,
            obs_stop=_mjd_to_utc(mjd_stop)   if mjd_stop  else None,
            mjd_start=mjd_start,
            mjd_stop=mjd_stop,
            ra_center=_safe_float(row.get("s_ra")),
            dec_center=_safe_float(row.get("s_dec")),
            em_min=em_min,
            em_max=em_max,
            em_min_um=round(em_min * 1e6, 4) if em_min else None,
            em_max_um=round(em_max * 1e6, 4) if em_max else None,
            exptime=_safe_float(row.get("t_exptime")),
            calib_level=_safe_int(row.get("calib_level")),
            instrument=str(row.get("instrument_name") or ""),
            facility=str(row.get("facility_name") or ""),
            s_region=str(row.get("s_region") or ""),
        )
    except Exception as exc:
        logger.debug("Row parse failure: %s — %s", exc, row)
        return None


async def _query_sia(
    client: httpx.AsyncClient,
    collection: str,
    ra: float,
    dec: float,
    radius_deg: float,
    maxrec: int = 25,
) -> list[ObservationRecord]:
    """
    Execute one SIA v2 query and return parsed ObservationRecord list.
    Raises httpx.HTTPStatusError on non-2xx; caller handles retries.
    """
    params = {
        "COLLECTION": collection,
        "POS": f"CIRCLE {ra} {dec} {radius_deg}",
        "CALIB": "2",           # Level-2 calibrated science products only
        "MAXREC": str(maxrec),
    }
    url = f"{settings.irsa_sia_url}?{urlencode(params)}"
    logger.info("SIA query → %s", url)

    timeout = max(settings.http_timeout, 45.0)
    resp = await client.get(url, timeout=timeout)
    resp.raise_for_status()

    rows: list[dict] = []
    content_type = resp.headers.get("content-type", "").lower()
    raw_content = resp.content.strip()

    # Check for VOTable XML response
    if "votable" in content_type or "xml" in content_type or raw_content.startswith(b"<?xml"):
        try:
            import io
            from astropy.io.votable import parse_single_table
            table = parse_single_table(io.BytesIO(resp.content))
            field_names = [f.name for f in table.fields]
            for arr_row in table.array:
                row_dict = {}
                for i, name in enumerate(field_names):
                    val = arr_row[i]
                    if isinstance(val, (bytes, bytearray)):
                        val = val.decode("utf-8", errors="replace")
                    row_dict[name] = val
                rows.append(row_dict)
        except Exception as exc:
            logger.warning("VOTable parse error for %s: %s", collection, exc)

    # Fallback to JSON parsing if no VOTable rows found
    if not rows:
        try:
            body = resp.json()
            if isinstance(body, list):
                rows = body
            elif isinstance(body, dict):
                for key in ("data", "results", "rows", "table"):
                    if key in body and isinstance(body[key], list):
                        rows = body[key]
                        break
        except Exception as exc:
            logger.debug("SIA response is not JSON (%s): %s", collection, exc)

    records = [r for r in (_parse_row(row, collection) for row in rows) if r is not None]
    logger.info("SIA %s → %d records (raw=%d)", collection, len(records), len(rows))
    return records


async def _query_with_retry(
    client: httpx.AsyncClient,
    collection: str,
    ra: float,
    dec: float,
    radius_deg: float,
    max_attempts: int = 3,
) -> list[ObservationRecord]:
    """Retry wrapper with exponential back-off and jitter."""
    delay = 1.0
    for attempt in range(1, max_attempts + 1):
        try:
            async with _sem:
                return await _query_sia(client, collection, ra, dec, radius_deg)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 or exc.response.status_code >= 500:
                if attempt < max_attempts:
                    sleep = delay + random.uniform(0, delay * 0.5)
                    logger.warning("SIA %s HTTP %d, retry %d in %.1fs",
                                   collection, exc.response.status_code, attempt, sleep)
                    await asyncio.sleep(sleep)
                    delay *= 2
                    continue
            logger.error("SIA %s HTTP %d (non-retryable)", collection, exc.response.status_code)
            return []
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
            if attempt < max_attempts:
                sleep = delay + random.uniform(0, delay * 0.5)
                logger.warning("SIA %s network error: %s, retry %d in %.1fs",
                               collection, exc, attempt, sleep)
                await asyncio.sleep(sleep)
                delay *= 2
            else:
                logger.error("SIA %s failed after %d attempts: %s", collection, max_attempts, exc)
                return []
        except Exception as exc:
            logger.error("SIA %s unexpected error: %s", collection, exc)
            return []
    return []


# ── Public API ────────────────────────────────────────────────────────────────


async def search_observations(
    ra: float,
    dec: float,
    radius_deg: float = 0.15,
) -> tuple[list[ObservationRecord], list[str]]:
    """
    Search QR3 then QR2 in parallel; deduplicate by obs_id.

    Returns:
        (records sorted newest-first, warnings list)
    """
    warnings: list[str] = []

    async with httpx.AsyncClient(
        headers={"User-Agent": "SPHEREx-SkyExplorer/1.0 (NASA Space Apps 2026)"},
        follow_redirects=True,
    ) as client:
        # Fire QR3 + QR2 concurrently
        qr3_task = asyncio.create_task(
            _query_with_retry(client, settings.preferred_release, ra, dec, radius_deg)
        )
        qr2_task = asyncio.create_task(
            _query_with_retry(client, settings.fallback_release, ra, dec, radius_deg)
        )
        qr3_records, qr2_records = await asyncio.gather(qr3_task, qr2_task)

    if not qr3_records:
        warnings.append("QR3 returned no results for this region.")
    if not qr2_records:
        warnings.append("QR2 returned no results for this region.")

    # Merge: prefer QR3 over QR2 for same position; deduplicate by obs_id
    seen: set[str] = set()
    merged: list[ObservationRecord] = []
    for rec in qr3_records + qr2_records:
        if rec.obs_id not in seen:
            seen.add(rec.obs_id)
            merged.append(rec)

    if not merged:
        warnings.append("No SPHEREx observations found in this region from either QR2 or QR3.")

    # Sort newest-first by obs_start (None goes last)
    merged.sort(
        key=lambda r: r.mjd_start if r.mjd_start is not None else 0.0,
        reverse=True,
    )
    return merged, warnings
