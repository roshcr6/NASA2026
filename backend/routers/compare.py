"""Compare router — validates compatibility of two observations."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from config import settings
from irsa_client import search_observations
from models import CompareResponse
from validation import validate_coordinates

router = APIRouter(tags=["compare"])
logger = logging.getLogger(__name__)


def _wavelength_overlap(
    em_min_a: Optional[float], em_max_a: Optional[float],
    em_min_b: Optional[float], em_max_b: Optional[float],
) -> Optional[list[float]]:
    """Return [overlap_min_um, overlap_max_um] or None if no overlap or unknown."""
    if None in (em_min_a, em_max_a, em_min_b, em_max_b):
        return None
    lo = max(em_min_a, em_min_b)
    hi = min(em_max_a, em_max_b)
    if lo >= hi:
        return None
    return [round(lo * 1e6, 4), round(hi * 1e6, 4)]


def _compatibility_notes(first, second) -> tuple[bool, list[str]]:
    notes: list[str] = []
    compatible = True

    # Time delta
    if first.mjd_start and second.mjd_start:
        delta = abs(first.mjd_start - second.mjd_start)
        notes.append(f"Time separation: {delta:.1f} days.")
        if delta < 1.0:
            notes.append("WARNING: Observations are < 1 day apart — may not represent independent epochs.")
            compatible = False

    # Wavelength compatibility
    overlap = _wavelength_overlap(first.em_min, first.em_max, second.em_min, second.em_max)
    if overlap is None:
        notes.append("WARNING: Wavelength coverage unknown or non-overlapping — spectral comparison unreliable.")
        compatible = False
    else:
        notes.append(f"Wavelength overlap: {overlap[0]}–{overlap[1]} µm.")
        if (overlap[1] - overlap[0]) < 0.05:
            notes.append("WARNING: Wavelength overlap is narrow (< 0.05 µm) — photometric comparison uncertain.")

    # Same collection?
    if first.collection != second.collection:
        notes.append(
            f"NOTE: Observations are from different releases ({first.collection} vs {second.collection}). "
            "Calibration differences may affect visual comparison."
        )

    notes.append(
        "IMPORTANT: This is a VISUAL comparison only. "
        "Brightness differences are not confirmed detections of moving objects."
    )
    return compatible, notes


@router.get("/compare", response_model=CompareResponse, summary="Compare two SPHEREx observations")
async def compare_observations(
    first_id: str = Query(..., description="obs_id of first observation"),
    second_id: str = Query(..., description="obs_id of second observation"),
    ra: float = Query(..., description="Reference RA (degrees)"),
    dec: float = Query(..., description="Reference Dec (degrees)"),
    size: float = Query(0.1, description="Cutout size for previews (degrees)"),
):
    """
    Return metadata and compatibility assessment for two observations.

    Does not perform pixel-level subtraction. Provides the information needed
    for a visual blink comparison, along with explicit scientific caveats.
    """
    validate_coordinates(ra, dec)

    if first_id == second_id:
        raise HTTPException(status_code=422, detail="first_id and second_id must be different.")

    records, warnings = await search_observations(ra, dec, radius_deg=0.3)
    by_id = {r.obs_id: r for r in records}

    first = by_id.get(first_id)
    second = by_id.get(second_id)

    if first is None:
        raise HTTPException(status_code=404, detail=f"Observation {first_id!r} not found.")
    if second is None:
        raise HTTPException(status_code=404, detail=f"Observation {second_id!r} not found.")

    # Ensure newer first for consistent blink order
    if first.mjd_start and second.mjd_start and first.mjd_start < second.mjd_start:
        first, second = second, first

    compatible, notes = _compatibility_notes(first, second)

    time_delta = None
    if first.mjd_start and second.mjd_start:
        time_delta = abs(first.mjd_start - second.mjd_start)

    overlap = _wavelength_overlap(first.em_min, first.em_max, second.em_min, second.em_max)

    base = f"http://localhost:8000/api/preview"
    return CompareResponse(
        first=first,
        second=second,
        compatible=compatible,
        compatibility_notes=notes,
        first_preview_url=f"{base}/{first.obs_id}?ra={ra}&dec={dec}&collection={first.collection}&size={size}",
        second_preview_url=f"{base}/{second.obs_id}?ra={ra}&dec={dec}&collection={second.collection}&size={size}",
        time_delta_days=time_delta,
        wavelength_overlap_um=overlap,
    )
