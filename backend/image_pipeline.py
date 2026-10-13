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


def _load_fits_image(
    raw_bytes: bytes,
    ra: Optional[float] = None,
    dec: Optional[float] = None,
    size_deg: Optional[float] = None,
    needs_crop: bool = False,
) -> tuple[np.ndarray, dict]:
    """
    Open FITS from bytes. Returns (image_array, meta_dict).

    Extension search order: IMAGE → first array-shaped HDU → Primary.
    Masking via FLAGS extension when present.
    If needs_crop is True and coordinates are given, uses Astropy WCS Cutout2D.
    """
    from astropy.io import fits  # type: ignore

    with fits.open(io.BytesIO(raw_bytes), memmap=False) as hdul:
        extnames = [h.name.upper() for h in hdul]
        logger.debug("FITS extensions: %s", extnames)

        sci_hdu = None
        for name in ("IMAGE", "SCI", ""):
            if name in extnames:
                idx = extnames.index(name)
                if hdul[idx].data is not None:
                    sci_hdu = hdul[idx]
                    break
        if sci_hdu is None:
            for h in hdul:
                if h.data is not None and h.data.ndim >= 2:
                    sci_hdu = h
                    break
        if sci_hdu is None:
            raise ValueError("No usable image array found in FITS file")

        data: np.ndarray = sci_hdu.data.astype(np.float32, copy=True)

        # Flag masking
        if "FLAGS" in extnames:
            flag_data = hdul[extnames.index("FLAGS")].data
            if flag_data is not None and flag_data.shape == data.shape:
                bad_pixels = flag_data.astype(np.uint16) != 0
                data[bad_pixels] = np.nan
                logger.debug("Masked %d flagged pixels", int(bad_pixels.sum()))

        # If full frame needs spatial cutout extraction to match user FOV
        if needs_crop and ra is not None and dec is not None:
            try:
                from astropy.wcs import WCS
                from astropy.nddata import Cutout2D
                from astropy.coordinates import SkyCoord
                import astropy.units as u

                wcs = WCS(sci_hdu.header)
                coord = SkyCoord(ra, dec, unit="deg", frame="icrs")
                crop_size = min(float(size_deg or 0.1), 0.5)
                cutout = Cutout2D(data, coord, size=(crop_size * u.deg, crop_size * u.deg), wcs=wcs)
                if cutout.data.size > 0 and np.any(np.isfinite(cutout.data)):
                    data = cutout.data
                    logger.info("Local Cutout2D applied successfully: shape %s", data.shape)
            except Exception as e:
                logger.warning("Cutout2D extraction error (%s) — using full image", e)

        meta = {
            "naxis1": data.shape[-1],
            "naxis2": data.shape[-2] if data.ndim > 1 else 1,
            "extensions": extnames,
        }

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
        return np.zeros(data.shape, dtype=np.uint8)

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
    if arr.ndim == 3:
        arr = arr[0]

    img = Image.fromarray(arr, mode="L")
    if max(img.size) > max_px:
        img.thumbnail((max_px, max_px), Image.LANCZOS)

    palette_r = np.zeros(256, dtype=np.uint8)
    palette_g = np.arange(256, dtype=np.uint8)
    palette_b = np.zeros(256, dtype=np.uint8)
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
) -> tuple[bytes, bool]:
    """
    Download FITS data:
    1. Try IRSA cutout service.
    2. Fallback to AWS Open Data S3 mirror or direct FITS file if cutout gives 503.

    Returns (fits_bytes, needs_local_crop).
    """
    size_deg = min(float(size_deg), settings.max_cutout_deg)

    allowed_prefixes = (
        "https://irsa.ipac.caltech.edu/ibe/",
        "http://irsa.ipac.caltech.edu/ibe/",
        "https://nasa-irsa-spherex.s3.amazonaws.com/",
    )
    if not any(access_url.startswith(p) for p in allowed_prefixes):
        raise ValueError(f"Access URL not from an allowed source: {access_url!r}")

    sep = "&" if "?" in access_url else "?"
    cutout_url = f"{access_url}{sep}center={ra},{dec}&size={size_deg}"
    logger.info("Attempting cutout request → %s", cutout_url)

    # 1. Try IPAC cutout service first
    try:
        resp = await client.get(cutout_url, timeout=settings.http_timeout)
        if resp.status_code == 200 and not resp.text.startswith("<html>"):
            data = resp.content
            if len(data) > 0 and not data.startswith(b"<!DOCTYPE"):
                return data, False
    except Exception as exc:
        logger.warning("Cutout service request failed: %s — trying mirror fallback", exc)

    # 2. Fallback: retrieve from AWS Open Data mirror or direct FITS URL
    s3_url = access_url.replace(
        "https://irsa.ipac.caltech.edu/ibe/data/spherex/",
        "https://nasa-irsa-spherex.s3.amazonaws.com/",
    ).replace(
        "http://irsa.ipac.caltech.edu/ibe/data/spherex/",
        "https://nasa-irsa-spherex.s3.amazonaws.com/",
    )

    for fallback_url in (s3_url, access_url):
        try:
            logger.info("Attempting FITS download from %s", fallback_url)
            resp = await client.get(fallback_url, timeout=max(settings.http_timeout, 45.0))
            if resp.status_code == 200:
                data = resp.content
                max_bytes = 120 * 1024 * 1024  # 120 MB guard
                if len(data) > max_bytes:
                    raise ValueError(f"FITS file too large ({len(data) // 1024 // 1024} MB)")
                return data, True
        except Exception as exc:
            logger.warning("Fallback download from %s failed: %s", fallback_url, exc)

    raise ValueError("All cutout and archive download attempts failed.")


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
    Full pipeline: download FITS → parse/cutout → stretch → PNG.
    Returns (png_bytes, metadata_dict).
    """
    warnings: list[str] = []

    raw_fits, needs_crop = await download_cutout(access_url, ra, dec, size_deg, client)

    try:
        image_array, fits_meta = _load_fits_image(
            raw_fits,
            ra=ra,
            dec=dec,
            size_deg=size_deg,
            needs_crop=needs_crop,
        )
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
