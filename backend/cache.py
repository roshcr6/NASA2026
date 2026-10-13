"""
Disk-backed preview cache.

Key: sha256 of (obs_id + ra + dec + size_deg + collection)
Entry: PNG file + JSON sidecar with metadata.
Thread-safe via asyncio.Lock (single-process deployment).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(settings.cache_dir)
_lock = asyncio.Lock()


def _ensure_cache_dir() -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_key(obs_id: str, ra: float, dec: float, size_deg: float, collection: str) -> str:
    raw = f"{obs_id}|{ra:.6f}|{dec:.6f}|{size_deg:.6f}|{collection}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _png_path(key: str) -> Path:
    return _CACHE_DIR / f"{key}.png"


def _meta_path(key: str) -> Path:
    return _CACHE_DIR / f"{key}.json"


def _is_expired(key: str, ttl: int) -> bool:
    p = _png_path(key)
    if not p.exists():
        return True
    age = time.time() - p.stat().st_mtime
    return age > ttl


async def get_preview(
    obs_id: str, ra: float, dec: float, size_deg: float, collection: str
) -> Optional[tuple[bytes, dict]]:
    """Return (png_bytes, meta) if cache hit and not expired, else None."""
    _ensure_cache_dir()
    key = _cache_key(obs_id, ra, dec, size_deg, collection)

    if _is_expired(key, settings.preview_cache_ttl):
        return None

    try:
        png = _png_path(key).read_bytes()
        meta = json.loads(_meta_path(key).read_text()) if _meta_path(key).exists() else {}
        return png, meta
    except Exception as exc:
        logger.warning("Cache read failure for key %s: %s", key, exc)
        return None


async def put_preview(
    obs_id: str,
    ra: float,
    dec: float,
    size_deg: float,
    collection: str,
    png_bytes: bytes,
    meta: dict,
) -> None:
    """Atomically write PNG + metadata sidecar to cache."""
    _ensure_cache_dir()
    key = _cache_key(obs_id, ra, dec, size_deg, collection)

    png_p  = _png_path(key)
    meta_p = _meta_path(key)
    tmp_png  = png_p.with_suffix(".tmp")
    tmp_meta = meta_p.with_suffix(".tmpmeta")

    async with _lock:
        try:
            tmp_png.write_bytes(png_bytes)
            tmp_meta.write_text(json.dumps(meta))
            tmp_png.replace(png_p)
            tmp_meta.replace(meta_p)
            logger.debug("Cached preview %s (%d bytes)", key, len(png_bytes))
        except Exception as exc:
            logger.error("Cache write failure for key %s: %s", key, exc)
            tmp_png.unlink(missing_ok=True)
            tmp_meta.unlink(missing_ok=True)


def cache_entry_count() -> int:
    _ensure_cache_dir()
    return len(list(_CACHE_DIR.glob("*.png")))
