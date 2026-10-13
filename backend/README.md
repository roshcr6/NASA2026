# SPHEREx Sky Explorer — Backend

## Requirements
- Python 3.12+
- See requirements.txt

## Setup
```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

## Run (development)
```bash
uvicorn main:app --reload --port 8000
```

## Environment
Copy `.env.example` to `.env` and adjust as needed.

## API Endpoints
- `GET /health` — service health
- `GET /api/observations?ra=&dec=&radius=` — search SPHEREx observations
- `GET /api/timeline?ra=&dec=` — observation timeline
- `GET /api/preview/{obs_id}?ra=&dec=&collection=&size=` — PNG preview
- `GET /api/compare?first_id=&second_id=&ra=&dec=` — compare two observations
- `GET /docs` — OpenAPI documentation (debug mode only)

## Attribution
SPHEREx data: JPL/Caltech/NASA via IRSA/IPAC.
DOI QR2: 10.26131/IRSA652 | DOI QR3: 10.26131/IRSA662
