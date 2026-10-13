# SPHEREx Sky Explorer — Project State & Handoff Document

**Project**: SPHEREx Sky Explorer  
**Event**: 2026 NASA Space Apps Challenge — Planet X and SPHEREx  
**Last Verified Date**: October 13, 2026  
**Status**: 3D-First Interactive Architecture Complete, Real NASA Data Integration Active, 11/11 Backend Tests Passing, 0 Lint Warnings/Errors, Production Next.js Build Passing.

---

## 1. Executive Summary & Verified Implementation

SPHEREx Sky Explorer is a public-facing, 3D-first astronomical web application that enables users to explore genuine NASA SPHEREx observations on an interactive celestial sphere, compare multi-epoch observations across time using an interactive blink comparator and side-by-side viewer, and investigate apparent sky variations responsibly.

### What Is Verifiably Implemented and Tested:

- **Interactive 3D Celestial Environment (Three.js + Canvas)**:
  - **On-Demand Rendering Architecture**: 0% idle GPU utilization; renders only during camera manipulation, timeline transitions, or animation cycles.
  - **Accurate ICRS Astronomical Coordinates**: Spherical-to-Cartesian mappings ($RA \in [0^\circ, 360^\circ]$, $Dec \in [-90^\circ, +90^\circ]$).
  - **Astronomical Overlays**: Celestial Equator, Right Ascension meridians (every 30°), Declination parallels (every 15°), Galactic plane curve, and background celestial source guides.
  - **Smooth Camera Transitions (`CameraDirector.ts`)**: Interruptible camera transitions with smooth cubic-spline easing toward target coordinates, user-breakout detection, and immediate bypass for `prefers-reduced-motion`.
  - **Observation Projection Patch (`ObservationImagePatch.ts`)**: Real SPHEREx Level-2 cutout images projected onto the celestial sphere at exact $(RA, Dec)$ positions with proper GPU texture disposal.
  - **Accessible 2D Planisphere Fallback (`Planisphere2D.tsx`)**: Full 2D canvas alternative with interactive RA/Dec navigation, coordinates readout, and target selection when WebGL is unavailable or reduced-motion is requested.

- **NASA IRSA SIA v2 Real Data Ingestion**:
  - Live querying of IRSA Simple Image Access (SIA) v2 service (`https://irsa.ipac.caltech.edu/SIA`) supporting VOTable XML parsing via Astropy.
  - Successfully tested and verified live retrieval of 13 genuine SPHEREx Level-2 Spectral Image observation epochs for the Galactic Anti-Center demonstration region (`RA=86.0`, `Dec=0.0`).

- **FITS Processing & Resilient Preview Pipeline**:
  - `image_pipeline.py` downloads Level-2 SPHEREx FITS products.
  - Automatic fallback between IPAC on-premises cutout service and official AWS Open Data S3 mirror (`arn:aws:s3:::nasa-irsa-spherex/qr2/level2` / `https://nasa-irsa-spherex.s3.amazonaws.com/`).
  - Spatial cutout extraction using `astropy.nddata.Cutout2D` and `astropy.wcs.WCS`.
  - Scientific extension inspection (`PRIMARY`, `IMAGE`, `FLAGS`, `VARIANCE`, `ZODI`, `PSF`, `WCS-WAVE`).
  - Data quality flag masking (`FLAGS` array) and `asinh` percentile-clipped non-linear contrast stretch.
  - False-colour infrared visualization with PNG output.

- **Backend API (FastAPI)**:
  - `GET /health`: Service health and IRSA upstream reachability check.
  - `GET /api/observations`: Discovers observations for sky coordinates with in-process TTL caching.
  - `GET /api/preview/{obs_id}`: Generates or retrieves cached PNG cutouts with atomic file caching and SSRF guards.
  - `GET /api/compare`: Evaluates epoch compatibility, time delta in days, wavelength overlap range, and attaches scientific caveats.

- **Frontend (Next.js 16.4 + React 19 + Tailwind CSS v4 + Three.js)**:
  - **Interactive Landing Page (`/`)**: Embedded interactive 3D celestial sphere preview, mission overview, workflow steps, and scientific integrity notices.
  - **Sky Explorer Workspace (`/explorer`)**:
    - Seamless toggle between 3D Celestial Sphere and 2D Planisphere.
    - Coordinate search & demonstration target quick-selection (Galactic Anti-Center, NEP, Kepler Field).
    - Multi-epoch chronological observation timeline carousel.
    - Dual comparison modes: Side-by-Side comparison and Blink Comparator (with adjustable blink rate and cross-fade).
    - Scientific Investigation Panel: Instrument channel, observation MJD/UTC dates, wavelength bounds, calibration release, and quality assessment.
    - **Evidence Dossier Modal (`EvidenceReportModal.tsx`)**: One-click generation and download of complete, verifiable JSON and Markdown evidence dossiers ("Save Evidence" stage) with full provenance, observation IDs, coordinates, and scientific caveats.

---

## 2. Technical Architecture & File Map

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
│   │   ├── page.tsx           # Landing page with 3D preview and observatory launch
│   │   └── explorer/
│   │       ├── layout.tsx     # Explorer metadata
│   │       └── page.tsx       # Explorer workspace: 3D/2D views, Timeline, Compare, Blink
│   ├── components/
│   │   ├── celestial/
│   │   │   ├── coordinateMath.ts       # ICRS RA/Dec <-> 3D Cartesian transforms
│   │   │   ├── CelestialGrid.ts        # Equator, meridians, parallels, Galactic plane
│   │   │   ├── ObservationMarkers.ts   # Sky target reticle, disks & footprints
│   │   │   ├── CameraDirector.ts       # Smooth, interruptible fly-to camera controller
│   │   │   ├── ObservationImagePatch.ts# 3D spherical projection of real SPHEREx PNG
│   │   │   ├── Planisphere2D.tsx       # 2D canvas fallback planisphere
│   │   │   └── CelestialSphereCanvas.tsx # Primary 3D WebGL controller (on-demand rendering)
│   │   └── investigation/
│   │       └── EvidenceReportModal.tsx # Exportable JSON & Markdown evidence dossiers
│   ├── lib/
│   │   ├── api.ts             # Typed client fetch wrapper with error normalisation
│   │   └── types.ts           # TypeScript interfaces matching backend models
│   ├── package.json           # Next.js 16, React 19, Three.js, Lucide, Tailwind v4
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
Ran 11 tests in 1.219s
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

### Frontend TypeScript & Lint:
Command: `npx tsc --noEmit` & `npm run lint`
Output:
```
> eslint
(Exited with code 0 — 0 errors, 0 warnings)
```

### Frontend Production Build:
Command: `npm run build`
Output:
```
▲ Next.js 16.4.0 (Turbopack)
✓ Compiled successfully in 545ms
✓ Generating static pages using 6 workers (5/5) in 558ms
Route (app)
┌ ○ /
├ ○ /_not-found
└ ○ /explorer
```

---

## 4. Scientific Integrity Inside the 3D Experience

1. **Directional Coordinates vs Depth**: Astronomical coordinates describe directions on the celestial sphere ($RA, Dec$). Depth is not arbitrarily fabricated; objects sit on a geometrically accurate celestial sphere model.
2. **Real Observations vs Decorative Elements**: Procedural background guide stars are explicitly labelled and distinct from real catalogued detections.
3. **Multi-Epoch Variations**: Visual differences between epochs are labelled with strict scientific responsibility ("observed change", "candidate signal") along with instrument calibration releases (QR2 vs QR3), spectral coverage bands ($0.75-5.0\,\mu\text{m}$), and MJD timestamps. They are never prematurely claimed as confirmed discoveries.
4. **Full Provenance Preservation**: All exported evidence dossiers (`.json` and `.md`) include instrument IDs, pipeline versions, WCS coordinates, time deltas, and data attribution (`SPHEREx/IRSA/IPAC/JPL/Caltech/NASA`).
