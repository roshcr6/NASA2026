"""
Unit and integration test suite for SPHEREx Sky Explorer backend.
Tests data validation, FITS processing, caching, comparison logic, and API endpoints.
"""
import io
import os
import unittest
from datetime import datetime, timezone
import numpy as np
from astropy.io import fits
from fastapi.testclient import TestClient

from main import app
from validation import validate_coordinates, validate_radius, validate_size, sanitise_obs_id
from image_pipeline import _asinh_stretch, _array_to_png, _load_fits_image
from routers.compare import _wavelength_overlap, _compatibility_notes
from models import ObservationRecord
import cache


class TestValidation(unittest.TestCase):
    def test_valid_coordinates(self):
        # Should not raise
        validate_coordinates(0.0, 0.0)
        validate_coordinates(180.5, -45.0)
        validate_coordinates(359.99, 89.99)

    def test_invalid_coordinates(self):
        with self.assertRaises(Exception):
            validate_coordinates(-1.0, 0.0)
        with self.assertRaises(Exception):
            validate_coordinates(360.1, 0.0)
        with self.assertRaises(Exception):
            validate_coordinates(100.0, 95.0)
        with self.assertRaises(Exception):
            validate_coordinates(100.0, -95.0)

    def test_validate_radius_and_size(self):
        validate_radius(0.1)
        validate_size(0.2)
        with self.assertRaises(Exception):
            validate_radius(-0.1)
        with self.assertRaises(Exception):
            validate_radius(1.0)
        with self.assertRaises(Exception):
            validate_size(1.0)

    def test_sanitise_obs_id(self):
        self.assertEqual(sanitise_obs_id("2026W12_1A_0477_2"), "2026W12_1A_0477_2")
        with self.assertRaises(Exception):
            sanitise_obs_id("../../../etc/passwd")


class TestImagePipeline(unittest.TestCase):
    def test_asinh_stretch_and_png(self):
        arr = np.linspace(10.0, 1000.0, 100 * 100, dtype=np.float32).reshape((100, 100))
        stretched = _asinh_stretch(arr)
        self.assertEqual(stretched.shape, (100, 100))
        self.assertEqual(stretched.dtype, np.uint8)
        self.assertTrue(stretched.max() > stretched.min())

        png_bytes = _array_to_png(stretched)
        self.assertTrue(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_nan_handling_in_stretch(self):
        arr = np.full((50, 50), np.nan, dtype=np.float32)
        stretched = _asinh_stretch(arr)
        self.assertEqual(stretched.shape, (50, 50))
        self.assertEqual(int(stretched.max()), 0)

    def test_fits_loading_with_flags(self):
        # Create synthetic FITS in memory
        primary = fits.PrimaryHDU()
        data = np.ones((64, 64), dtype=np.float32) * 50.0
        data[10, 10] = 5000.0  # star
        sci = fits.ImageHDU(data=data, name="IMAGE")
        sci.header["WAVE"] = 2.5e-6  # 2.5 microns

        flags = np.zeros((64, 64), dtype=np.int16)
        flags[10, 10] = 1  # mark bad pixel
        flag_hdu = fits.ImageHDU(data=flags, name="FLAGS")

        hdul = fits.HDUList([primary, sci, flag_hdu])
        buf = io.BytesIO()
        hdul.writeto(buf)
        buf.seek(0)
        raw_bytes = buf.getvalue()

        loaded_data, meta = _load_fits_image(raw_bytes)
        self.assertEqual(loaded_data.shape, (64, 64))
        self.assertTrue(np.isnan(loaded_data[10, 10]))  # Flagged pixel masked to NaN
        self.assertEqual(meta.get("wavelength_um"), 2.5)


class TestComparisonLogic(unittest.TestCase):
    def test_wavelength_overlap(self):
        # 1.0 - 2.0 um and 1.5 - 2.5 um -> overlap 1.5 - 2.0 um
        overlap = _wavelength_overlap(1.0e-6, 2.0e-6, 1.5e-6, 2.5e-6)
        self.assertIsNotNone(overlap)
        self.assertAlmostEqual(overlap[0], 1.5)
        self.assertAlmostEqual(overlap[1], 2.0)

        # Disjoint ranges -> None
        disjoint = _wavelength_overlap(1.0e-6, 1.4e-6, 1.5e-6, 2.0e-6)
        self.assertIsNone(disjoint)

    def test_compatibility_notes_flags_temporal_and_spectral_separation(self):
        now = datetime.now(timezone.utc)
        obs_a = ObservationRecord(
            obs_id="obs_A",
            collection="spherex_qr2",
            access_url="https://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/a.fits",
            mjd_start=60000.0,
            em_min=1.0e-6,
            em_max=2.0e-6,
        )
        obs_b = ObservationRecord(
            obs_id="obs_B",
            collection="spherex_qr2",
            access_url="https://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/b.fits",
            mjd_start=60180.0,  # 180 days later
            em_min=1.2e-6,
            em_max=2.2e-6,
        )
        compatible, notes = _compatibility_notes(obs_a, obs_b)
        self.assertTrue(compatible)
        self.assertTrue(any("180.0 days" in n for n in notes))


class TestAPIEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_endpoint(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("status", data)
        self.assertIn("irsa_reachable", data)
        self.assertIn("cache_entries", data)

    def test_validation_rejection_on_invalid_coords(self):
        resp = self.client.get("/api/observations?ra=500&dec=0")
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()
