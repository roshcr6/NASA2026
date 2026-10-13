"""Input validation helpers — coordinate bounds, parameter sanitisation."""
from __future__ import annotations

from fastapi import HTTPException


def validate_coordinates(ra: float, dec: float) -> None:
    """
    Validate ICRS coordinates.
    RA: [0, 360), Dec: [-90, 90].
    """
    if not (0.0 <= ra < 360.0):
        raise HTTPException(status_code=422, detail=f"RA must be in [0, 360); got {ra}")
    if not (-90.0 <= dec <= 90.0):
        raise HTTPException(status_code=422, detail=f"Dec must be in [-90, 90]; got {dec}")


def validate_radius(radius_deg: float, max_deg: float = 0.5) -> None:
    if radius_deg <= 0:
        raise HTTPException(status_code=422, detail="radius must be > 0")
    if radius_deg > max_deg:
        raise HTTPException(status_code=422, detail=f"radius must be ≤ {max_deg} degrees")


def validate_size(size_deg: float, max_deg: float = 0.5) -> None:
    if size_deg <= 0:
        raise HTTPException(status_code=422, detail="size must be > 0")
    if size_deg > max_deg:
        raise HTTPException(status_code=422, detail=f"size must be ≤ {max_deg} degrees")


def sanitise_obs_id(obs_id: str) -> str:
    """Validate and sanitise observation ID — prevent path traversal."""
    if ".." in obs_id or "/" in obs_id or "\\" in obs_id:
        raise HTTPException(status_code=422, detail=f"Observation ID contains invalid characters: {obs_id!r}")
    allowed = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789-_."
    )
    cleaned = "".join(c for c in obs_id if c in allowed)
    if len(cleaned) < 4 or cleaned != obs_id:
        raise HTTPException(status_code=422, detail=f"Invalid observation ID: {obs_id!r}")
    return cleaned
