# SPHEREx Sky Explorer — Project State & Handoff Document

**Project**: SPHEREx Sky Explorer  
**Event**: 2026 NASA Space Apps Challenge — Planet X and SPHEREx  
**Last Verified Date**: October 13, 2026  
**Status**: Core Architecture Verified, Real NASA Data Integration Working, 11/11 Backend Tests Passing, Production Frontend Build & Lint Passing.

---

## 1. Executive Summary & Verified Implementation

SPHEREx Sky Explorer is a public-facing web application that enables users to explore genuine NASA SPHEREx observations, compare multi-epoch observations across time using an interactive blink comparator and side-by-side viewer, and investigate apparent sky variations responsibly.

### What Is Verifiably Implemented and Tested:
- **NASA IRSA SIA v2 Real Data Ingestion**:
  - Live querying of IRSA Simple Image Access (SIA) v2 service (`https://irsa.ipac.caltech.edu/SIA`) supporting VOTable XML parsing via Astropy.
  - Successfully tested and verified live retrieval of 13 genuine SPHEREx Level-2 Spectral Image observation epochs for the Galactic Anti-Center demonstration region (`RA=86.0`, `Dec=0.0`).
- **FITS Processing & Preview Pipeline**:
  - `image_pipeline.py` downloads Level-2 SPHEREx FITS products.
  - Automatic fallback between IPAC on-premises cutout service and the official AWS Open Data S3 mirror (`arn:aws:s3:::nasa-irsa-spherex/qr2/level2` / `https://nasa-irsa-spherex.s3.amazonaws.com/`).
  - Spatial cutout extraction using `astropy.nddata.Cutout2D` and `astropy.wcs.WCS`.
  - Scientific extension inspection (`PRIMARY`, `IMAGE`, `FLAGS`, `VARIANCE`, `ZODI`, `PSF`, `WCS-WAVE`).
  - Data quality flag masking (`FLAGS` array) and `asinh` percentile-clipped non-linear contrast stretch.
  - False-colour infrared visualization with PNG output.
- **Backend API (FastAPI)**:
  - `GET /health`: Service health and IRSA upstream reachability check.
  - `GET /api/observations`: Discovers observations for sky coordinates with in-process TTL caching.
  - `GET /api/preview/{obs_id}`: Generates or retrieves cached PNG cutouts with atomic file caching and SSRF guards.
  - `GET /api/compare`: Evaluates epoch compatibility, time delta in days, wavelength overlap range, and attaches scientific caveats.
- **Frontend (Next.js 16 + React 19 + Tailwind CSS v4)**:
  - Interactive Landing Page (`/`): Mission overview, workflow explanation, and scientific responsibility notices.
  - Sky Explorer Workspace (`/explorer`): Coordinate search panel, demonstration region presets, observation timeline carousel, side-by-side comparison, interactive blink comparator with adjustable speed and opacity, and detailed metadata panels.

---

## 2. Technical Architecture & File Map

### Repository Layout:
```
NASA/
├── backend/
│   ├── config.py              # Pydantic Settings (.env configuration)
│   ├── main.py                # FastAPI app entry point & CORS configuration
│   ├── models.py              # Pydantic models for Observations, Timeline, Compare
│   ├── irsa_client.py         # IRSA SIA v2 client with VOTable + JSON support
│   ├── image_pipeline.py      # FITS download, Cutout2D, asinh stretch, PNG pipeline
│   ├── cache.py               # Disk-backed preview cache with SHA-256 keys
│   ├── validation.py          # Coordinate, radius, size, and obs_id security validation
│   ├── routers/
│   │   ├── health.py          # /health endpoint
│   │   ├── observations.py    # /api/observations, /api/timeline
│   │   ├── preview.py         # /api/preview/{obs_id}
│   │   └── compare.py         # /api/compare
│   ├── test_pipeline.py       # Automated unit & integration test suite (11 tests)
│   └── requirements.txt       # fastapi, astropy, pillow, httpx, numpy, etc.
│
├── frontend/
│   ├── app/
│   │   ├── globals.css        # Cosmic dark theme tokens & Tailwind v4 imports
│   │   ├── layout.tsx         # Root layout with SEO and metadata
│   │   ├── page.tsx           # Landing page with animated star canvas
│   │   └── explorer/
│   │       ├── layout.tsx     # Explorer metadata
│   │       └── page.tsx       # Complete Explorer UI: Search, Timeline, Compare, Blink
│   ├── lib/
│   │   ├── api.ts             # Typed client fetch wrapper with error normalisation
│   │   └── types.ts           # TypeScript interfaces matching backend models
│   ├── package.json           # Next.js 16, React 19, Lucide, Tailwind v4
│   └── .env.local             # NEXT_PUBLIC_API_URL=http://localhost:8000
│
├── HANDOFF.md                 # This document
└── README.md
```

---

## 3. Verified Verification Results

### Backend Tests:
Command: `.\venv\Scripts\python.exe -m unittest test_pipeline.py`
Output:
```
Ran 11 tests in 11.961s
OK
```
Tests pass for:
1. Coordinate bound checks (`[0, 360)` and `[-90, 90]`).
2. Radius and cutout size limits.
3. Path traversal security protection in `sanitise_obs_id`.
4. Asinh contrast stretch and NaN resilience.
5. FITS image loading, extension inspection, and bad pixel flag masking.
6. Wavelength spectral overlap calculation.
7. Multi-epoch compatibility evaluation and warning generators.
8. API health and error handling.

### Frontend Production Build:
Command: `npm run build`
Output:
```
▲ Next.js 16.4.0 (Turbopack)
✓ Compiled successfully in 4.6s
✓ Generating static pages using 6 workers (5/5) in 616ms
Route (app)
┌ ○ /
├ ○ /_not-found
└ ○ /explorer
```

### Frontend Code Quality & Linting:
Command: `npm run lint`
Output:
```
> frontend@0.1.0 lint
> eslint
(Exited with code 0 — 0 errors, 0 warnings)
```

---

## 4. External Data Source Decisions & Discoveries

1. **IRSA SIA v2 Endpoint**:
   - URL: `https://irsa.ipac.caltech.edu/SIA`
   - Data release tested: `spherex_qr2` (active full coverage in archive; QR3 is probed concurrently with QR2 fallback).
   - Format: Returns IVOA VOTable XML (`application/x-votable+xml`). Parsed via `astropy.io.votable`.
   - `MAXREC`: Clamped to 25 to ensure sub-10s archive responses.
2. **FITS Cutouts & Mirroring**:
   - Primary IRSA Cutout: `https://irsa.ipac.caltech.edu/ibe/data/spherex/...fits?center=RA,Dec&size=DEG` (subject to 503 load shedding during peak hours).
   - Resilient Fallback: AWS Open Data public bucket `nasa-irsa-spherex` (`https://nasa-irsa-spherex.s3.amazonaws.com/qr2/level2/...`).
   - Local Sub-region Extraction: When full FITS is retrieved, `astropy.nddata.Cutout2D` crops the exact requested box using the FITS WCS header.
3. **Attribution & Provenance**:
   - Header `X-Data-Attribution: SPHEREx/IRSA/IPAC/JPL/Caltech/NASA` attached to all generated image previews.
   - All comparisons include explicit scientific caveats: visual changes are presented as "observed change" or "potential signals", never as confirmed discoveries.

---

## 5. Environment Configuration

### Backend (`backend/.env`):
- `PREFERRED_RELEASE=spherex_qr3`
- `FALLBACK_RELEASE=spherex_qr2`
- `CACHE_DIR=cache`
- `MAX_CONCURRENT_REQUESTS=6`
- `MAX_CUTOUT_DEG=0.5`
- `DEFAULT_CUTOUT_DEG=0.1`
- `HTTP_TIMEOUT=45.0`
- `DEBUG=True`

### Frontend (`frontend/.env.local`):
- `NEXT_PUBLIC_API_URL=http://localhost:8000`

---

## 6. Next Recommended Actions for Development
1. **Interactive Guided Tour**: Add a step-by-step interactive onboarding walkthrough on `/explorer` highlighting the 3 demonstration fields.
2. **Comparison Provenance Export**: Add a "Save Evidence" feature allowing users to export a JSON summary / comparison report with source observation IDs, MJD timestamps, coordinates, and preview image links.
3. **Difference Image Tool (Sub-priority)**: Add an optional normalized difference view `(Image B - Image A)` after sub-pixel alignment for advanced users.
