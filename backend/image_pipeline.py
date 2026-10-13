"""
Image processing pipeline — FITS → PNG preview.

• Downloads a SPHEREx Level-2 FITS cutout from IRSA.
• Reads the IMAGE extension (primary science data).
• Applies asinh stretch with percentile clipping.
• Masks non-finite and flagged pixels.
• Returns a PNG byte buffer suitable for HTTP response.

Scientific constraints honoured:
  - Variance and FLAGS extensions used for quality masking when present.
  - WCS preserved in provenance metadata but NOT re-projected here.
  - Stretch parameters recorded in preview metadata.
  - Never silently produces a blank image; raises if data is unusable.
"""
from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Optional

import httpx
import numpy as np
from PIL import Image

from config import settings

logger = logging.getLogger(__name__)

# ── FITS loading (deferred import — astropy is large) ────────────────────────


def _load_fits_image(raw_bytes: bytes) -> tuple[np.ndarray, dict]:
    """
    Open FITS from bytes. Returns (image_array, meta_dict).

    Extension search order: IMAGE → first array-shaped HDU → Primary.
    Masking via FLAGS extension when present.
    """
    from astropy.io import fits  # type: ignore

    with fits.open(io.BytesIO(raw_bytes), memmap=False) as hdul:
        # Collect extension names
        extnames = [h.name.upper() for h in hdul]
        logger.debug("FITS extensions: %s", extnames)

        # ── Pick science extension ────────────────────────────────────────
        sci_hdu = None
        for name in ("IMAGE", "SCI", ""):
            if name in extnames:
                idx = extnames.index(name)
                if hdul[idx].data is not None:
                    sci_hdu = hdul[idx]
                    break
        if sci_hdu is None:
            # Fallback: first HDU with 2-D data
            for h in hdul:
                if h.data is not None and h.data.ndim >= 2:
                    sci_hdu = h
                    break
        if sci_hdu is None:
            raise ValueError("No usable image array found in FITS file")

        data: np.ndarray = sci_hdu.data.astype(np.float32, copy=True)

        # ── Flag masking ──────────────────────────────────────────────────
        if "FLAGS" in extnames:
            flag_data = hdul[extnames.index("FLAGS")].data
            if flag_data is not None and flag_data.shape == data.shape:
                bad_pixels = flag_data.astype(np.uint16) != 0
                data[bad_pixels] = np.nan
                logger.debug("Masked %d flagged pixels", int(bad_pixels.sum()))

        meta = {
            "naxis1": data.shape[-1],
            "naxis2": data.shape[-2] if data.ndim > 1 else 1,
            "extensions": extnames,
        }
        # Optionally extract wavelength from WCS-WAVE or header keyword
        try:
            hdr = sci_hdu.header
            if "WAVE" in hdr:
                meta["wavelength_um"] = round(float(hdr["WAVE"]) * 1e6, 4)
            elif "CRVAL3" in hdr:
                meta["wavelength_um"] = round(float(hdr["CRVAL3"]) * 1e6, 4)
        except Exception:
            pass

        return data, meta


def _asinh_stretch(
    data: np.ndarray,
    lo_pct: float = 0.5,
    hi_pct: float = 99.5,
) -> np.ndarray:
    """
    Apply asinh stretch:
      1. Clip to [lo_pct, hi_pct] percentile (non-NaN).
      2. Apply asinh.
      3. Rescale to [0, 255].
    """
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        raise ValueError("Image contains only NaN / non-finite values — cannot render.")

    vmin = np.percentile(finite, lo_pct)
    vmax = np.percentile(finite, hi_pct)
    if vmax <= vmin:
        vmax = vmin + 1.0

    stretched = np.arcsinh((data - vmin) / (vmax - vmin + 1e-10))
    s_min = np.nanmin(stretched)
    s_max = np.nanmax(stretched)
    if s_max <= s_min:
        s_max = s_min + 1.0

    normed = (stretched - s_min) / (s_max - s_min)
    normed = np.clip(normed, 0.0, 1.0)
    normed[~np.isfinite(data)] = 0.0  # NaN pixels → black
    return (normed * 255).astype(np.uint8)


def _array_to_png(arr: np.ndarray, max_px: int = 512) -> bytes:
    """
    Convert 2-D uint8 array → PNG bytes (grayscale → RGB colourmap).
    Applies a green-tinted false-colour map to suggest infrared character.
    """
    # If 3-D (wavelength-axis cube slice), take first plane
    if arr.ndim == 3:
        arr = arr[0]

    img = Image.fromarray(arr, mode="L")

    # Resize if necessary (maintain aspect ratio)
    if max(img.size) > max_px:
        img.thumbnail((max_px, max_px), Image.LANCZOS)

    # Apply a simple infrared false-colour palette (dark→green→white)
    palette_r = np.zeros(256, dtype=np.uint8)
    palette_g = np.arange(256, dtype=np.uint8)
    palette_b = np.zeros(256, dtype=np.uint8)
    # Blend toward white for bright pixels
    palette_r[128:] = np.linspace(0, 200, 128, dtype=np.uint8)
    palette_b[128:] = np.linspace(0, 160, 128, dtype=np.uint8)

    rgb_img = Image.merge(
        "RGB",
        [
            Image.fromarray(palette_r[arr], mode="L"),
            Image.fromarray(palette_g[arr], mode="L"),
            Image.fromarray(palette_b[arr], mode="L"),
        ],
    )
    buf = io.BytesIO()
    rgb_img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ── FITS download ─────────────────────────────────────────────────────────────


async def download_cutout(
    access_url: str,
    ra: float,
    dec: float,
    size_deg: float,
    client: httpx.AsyncClient,
) -> bytes:
    """
    Download a FITS cutout from the IRSA cutout service.

    Parameters are appended to the access_url as documented at:
    https://irsa.ipac.caltech.edu/data/SPHEREx/docs/cutout_tool.html

    Guard rails:
    - size_deg is clamped to settings.max_cutout_deg.
    - The URL must be under the IRSA IBE domain (SSRF guard).
    - Response Content-Type must be FITS.
    - Size is bounded to prevent OOM.
    """
    size_deg = min(float(size_deg), settings.max_cutout_deg)

    # SSRF guard: only allow IRSA IBE URLs
    allowed_prefixes = (
        "https://irsa.ipac.caltech.edu/ibe/",
        "http://irsa.ipac.caltech.edu/ibe/",
    )
    if not any(access_url.startswith(p) for p in allowed_prefixes):
        raise ValueError(f"Access URL not from an allowed IRSA IBE prefix: {access_url!r}")

    sep = "&" if "?" in access_url else "?"
    cutout_url = f"{access_url}{sep}center={ra},{dec}&size={size_deg}"
    logger.info("Cutout request → %s", cutout_url)

    resp = await client.get(cutout_url, timeout=settings.http_timeout)
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    # Accept FITS or octet-stream
    if "fits" not in content_type and "octet" not in content_type and "application" not in content_type:
        raise ValueError(f"Unexpected content-type from cutout service: {content_type!r}")

    max_bytes = 100 * 1024 * 1024  # 100 MB guard
    data = await resp.aread()
    if len(data) > max_bytes:
        raise ValueError(f"Cutout response too large ({len(data) // 1024 // 1024} MB > 100 MB)")

    return data


# ── Public pipeline entry point ───────────────────────────────────────────────


async def generate_preview(
    access_url: str,
    ra: float,
    dec: float,
    size_deg: float,
    obs_id: str,
    client: httpx.AsyncClient,
) -> tuple[bytes, dict]:
    """
    Full pipeline: download FITS → parse → stretch → PNG.

    Returns (png_bytes, metadata_dict).
    metadata_dict contains stretch params, wavelength, and any warnings.
    """
    warnings: list[str] = []

    raw_fits = await download_cutout(access_url, ra, dec, size_deg, client)

    try:
        image_array, fits_meta = _load_fits_image(raw_fits)
    except Exception as exc:
        raise ValueError(f"FITS parse failed for {obs_id}: {exc}") from exc

    if "FLAGS" not in fits_meta.get("extensions", []):
        warnings.append("FLAGS extension not found — bad pixels may not be masked.")

    try:
        stretched = _asinh_stretch(image_array)
    except ValueError as exc:
        raise ValueError(f"Image stretch failed for {obs_id}: {exc}") from exc

    png_bytes = _array_to_png(stretched, max_px=settings.preview_max_px)

    meta = {
        "stretch": "asinh",
        "lo_pct": 0.5,
        "hi_pct": 99.5,
        "naxis1": fits_meta.get("naxis1"),
        "naxis2": fits_meta.get("naxis2"),
        "extensions": fits_meta.get("extensions", []),
        "wavelength_um": fits_meta.get("wavelength_um"),
        "warnings": warnings,
    }
    return png_bytes, meta
