# SPHEREx Sky Explorer — 3D Celestial Observatory

[![Challenge](https://img.shields.io/badge/NASA%20Space%20Apps-2026%20Challenge-blue.svg)](https://www.spaceappschallenge.org/2026/challenges/planet-x-and-spherex/)
[![SPHEREx](https://img.shields.io/badge/Data-SPHEREx%20QR2%2FQR3-purple.svg)](https://irsa.ipac.caltech.edu/Missions/spherex.html)
[![Backend](https://img.shields.io/badge/Backend-FastAPI%20%7C%20Astropy-green.svg)](https://fastapi.tiangolo.com/)
[![Frontend](https://img.shields.io/badge/Frontend-Next.js%2016%20%7C%20Three.js-cyan.svg)](https://nextjs.org/)

An interactive, 3D-first scientific astronomy web application built for the **2026 NASA Space Apps Challenge ("Planet X and SPHEREx")**. 

SPHEREx Sky Explorer connects directly to live NASA Infrared Science Archive (IRSA) data services, enabling public and professional users to explore genuine SPHEREx multi-epoch spectral images, navigate a high-performance 3D celestial sphere, compare observations across time with an interactive blink comparator, and export verified scientific evidence dossiers with complete provenance.

---

## Key Capabilities

### 1. Immersive 3D Celestial Navigation
- **True Astronomical Coordinates**: Built on the International Celestial Reference System (ICRS) mapping Right Ascension ($RA \in [0^\circ, 360^\circ]$) and Declination ($Dec \in [-90^\circ, +90^\circ]$) to a 3D celestial sphere.
- **Astronomical Overlays**: Renders the Celestial Equator, RA meridians (every 30°), Dec parallels (every 15°), and the Galactic plane curve.
- **On-Demand Rendering**: Custom Three.js render loop with **0% idle GPU usage**; only draws when the camera moves or transitions occur.
- **Cinematic & Interruptible Camera**: Fly-to navigation with cubic easing that immediately respects user gesture interruptions.
- **Accessible 2D Planisphere Fallback**: A complete canvas planisphere alternative with interactive cursor readouts for reduced-motion preferences or devices without WebGL.

### 2. Live NASA SPHEREx Ingestion & Resilient FITS Processing
- **IRSA SIA v2 Client**: Directly queries IPAC Simple Image Access v2 using Astropy's VOTable parser to discover Level-2 spectral images.
- **Dual-Source Resilient Fetching**: Seamless fallback between IPAC on-premises cutout service and the official AWS Open Data S3 mirror (`arn:aws:s3:::nasa-irsa-spherex/qr2/level2` / `https://nasa-irsa-spherex.s3.amazonaws.com/`) during high-traffic periods.
- **Astronomical Image Pipeline**: 
  - Sub-region spatial extraction via `astropy.nddata.Cutout2D` using exact WCS headers.
  - Extension inspection across `PRIMARY`, `IMAGE`, `FLAGS`, `VARIANCE`, `ZODI`, `PSF`, and `WCS-WAVE`.
  - Non-linear `asinh` percentile-clipped contrast stretch with NaN safety and bad-pixel mask filtering.
  - High-fidelity false-colour PNG preview generation.

### 3. Scientific Multi-Epoch Investigation
- **Chronological Timeline**: Interactive multi-epoch carousel displaying observation dates (MJD & UTC), central wavelengths ($0.75 - 5.0\,\mu\text{m}$), and data releases (QR2 / QR3).
- **Dual Comparison Modes**:
  - **Side-by-Side View**: Simultaneous inspection with synchronized coordinate crosshairs.
  - **Blink Comparator**: Adjustable blink frequency ($1 - 10\,\text{Hz}$) and opacity cross-fade to detect candidate transient signals or proper-motion objects.
- **Evidence Dossier Generation**: One-click generation and download of complete, verifiable `.json` and `.md` dossiers with exact WCS parameters, time deltas, data releases, and required scientific caveats.

### 4. Scientific Responsibility
- **Honest Evidence Labelling**: Visual variations are strictly categorized as "observed changes" or "candidate signals" with explicit warnings against premature confirmation of Planet X or solar-system discoveries.
- **Distinction Between Guides & Data**: Decorative guide stars are visually and programmatically segregated from genuine SPHEREx detections.

---

## Architecture Overview

```
NASA/
├── backend/
│   ├── config.py              # Pydantic Settings & environment validation
│   ├── main.py                # FastAPI app entry point & CORS configuration
│   ├── models.py              # Pydantic models for Observations, Timeline, Compare
│   ├── irsa_client.py         # IRSA SIA v2 client with VOTable + JSON support
│   ├── image_pipeline.py      # FITS download, Cutout2D, asinh stretch, PNG pipeline
│   ├── cache.py               # Disk-backed preview cache with SHA-256 keys
│   ├── validation.py          # Coordinate, radius, size, and obs_id security validation
│   ├── routers/
│   │   ├── health.py          # /health endpoint (probes upstream IRSA reachability)
│   │   ├── observations.py    # /api/observations, /api/timeline
│   │   ├── preview.py         # /api/preview/{obs_id}
│   │   └── compare.py         # /api/compare
│   └── test_pipeline.py       # Automated unit & integration test suite (11 tests)
│
├── frontend/
│   ├── app/
│   │   ├── globals.css        # Cosmic dark theme tokens & Tailwind CSS v4 imports
│   │   ├── layout.tsx         # Root layout with SEO and metadata
│   │   ├── page.tsx           # Landing page with embedded 3D celestial observatory
│   │   └── explorer/
│   │       ├── layout.tsx     # Explorer metadata
│   │       └── page.tsx       # Explorer workspace: 3D/2D views, Timeline, Compare, Blink
│   ├── components/
│   │   ├── celestial/
│   │   │   ├── coordinateMath.ts       # ICRS RA/Dec <-> 3D Cartesian transformations
│   │   │   ├── CelestialGrid.ts        # Equator, meridians, parallels, Galactic plane
│   │   │   ├── ObservationMarkers.ts   # Sky target reticles, disks & footprints
│   │   │   ├── CameraDirector.ts       # Smooth, interruptible fly-to camera controller
│   │   │   ├── ObservationImagePatch.ts# 3D spherical projection of real SPHEREx PNG
│   │   │   ├── Planisphere2D.tsx       # 2D canvas fallback planisphere
│   │   │   └── CelestialSphereCanvas.tsx # Primary 3D WebGL controller (on-demand rendering)
│   │   └── investigation/
│   │       └── EvidenceReportModal.tsx # Exportable JSON & Markdown evidence dossiers
│   └── lib/
│       ├── api.ts             # Typed client fetch wrapper with error normalisation
│       └── types.ts           # TypeScript interfaces matching backend models
│
├── HANDOFF.md                 # Complete project implementation & verification record
└── README.md
```

---

## Getting Started

### One-Click Launch (Windows)
Simply double-click or run:
```cmd
start.bat
```
This automatically verifies environments, installs missing frontend packages, starts the FastAPI backend (port 8000), starts the Next.js frontend (port 3000), and opens `http://localhost:3000` in your default browser.

---

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- Modern Web browser with WebGL 2.0 support

---

### Manual Setup

1. **Navigate to the backend directory**:
   ```bash
   cd backend
   ```

2. **Activate the virtual environment**:
   - Windows PowerShell:
     ```powershell
     .\venv\Scripts\Activate.ps1
     ```
   - macOS / Linux:
     ```bash
     source venv/bin/activate
     ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Start the FastAPI backend server**:
   ```bash
   python -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```

5. **Verify backend health**:
   ```bash
   curl http://127.0.0.1:8000/health
   ```
   Expected response:
   ```json
   {
     "status": "ok",
     "irsa_reachable": true,
     "cache_entries": 0,
     "version": "1.0.0"
   }
   ```

---

### Frontend Setup

1. **Navigate to the frontend directory**:
   ```bash
   cd frontend
   ```

2. **Install dependencies**:
   ```bash
   npm install
   ```

3. **Start the Next.js development server**:
   ```bash
   npm run dev
   ```

4. **Open in browser**:
   - Landing Page: [http://localhost:3000](http://localhost:3000)
   - 3D Celestial Explorer: [http://localhost:3000/explorer](http://localhost:3000/explorer)

---

## Automated Verification & Testing

### Backend Test Suite
The automated test suite verifies coordinate boundary enforcement, radius validation, path traversal security, `asinh` stretch algorithms, FITS loading and bad-pixel masking, wavelength overlap math, and API error handling:
```bash
cd backend
python -m unittest test_pipeline.py
```
*Expected: 11 tests passed in ~1.2s.*

### Frontend Typechecking & Linting
```bash
cd frontend
npx tsc --noEmit
npm run lint
```
*Expected: 0 errors, 0 warnings.*

### Production Build Verification
```bash
cd frontend
npm run build
```
*Expected: Production build successfully compiled with Turbopack.*

---

## Data Provenance & Attribution

- **Mission Data**: NASA Spectro-Photometer for the History of the Universe, Epoch of Reionization, and Ices Explorer (SPHEREx).
- **Archive Host**: NASA/IPAC Infrared Science Archive (IRSA), operated by the Jet Propulsion Laboratory, California Institute of Technology under contract with NASA.
- **Data Releases**:
  - Quick Release 2 (QR2) — DOI: `10.26131/IRSA652`
  - Quick Release 3 (QR3) — DOI: `10.26131/IRSA662`
- **S3 Mirror**: AWS Open Data Sponsorship Program (`arn:aws:s3:::nasa-irsa-spherex`).

---

## License

This project is developed for the 2026 NASA Space Apps Challenge and released under the MIT License. See [LICENSE](LICENSE) for details.
