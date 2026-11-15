# SPHEREx Sky – NASA Space Apps 2026 (Planet X and SPHEREx)

A public web tool for watching the infrared sky change over time with NASA SPHEREx data.

## Structure
| Folder | Owner | What |
|---|---|---|
| `science/` | Emil | `fetch_spherex.py`: IRSA query, cutouts, stacking, blink frames, spectrum |
| `backend/` | Erik | FastAPI: jobs, cache, warm-up, file serving |
| `frontend/` | Eliz, Juho | Web app: Image Viewer, coordinate input, Aladin, hosting |
| `examples/` | – | Example output for frontend development |

API and data format: **[CONTRACT.md](CONTRACT.md)**

## Setup (Python 3.10+)
```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Mac/Linux: source .venv/bin/activate)
pip install -r backend/requirements.txt
```

## Run the science script directly
```bash
python science/fetch_spherex.py --target barnard --per-group 3
python science/fetch_spherex.py --ra 133.795 --dec -7.245 --size 3 --per-group 3
```
`--per-group 3` fetches 3 images per epoch and detector (fast). `0` fetches everything (slow, full spectrum).

## Run the API
```bash
uvicorn backend.main:app --reload --port 8000
```
On startup it fetches the 5 challenge targets into `output/` (set `WARMUP=0` to skip).
Try: http://localhost:8000/api/targets and http://localhost:8000/docs

## Run the frontend
```bash
cd frontend && npm install && npm run dev
```
Backend address: `VITE_API_BASE_URL`. Without it the app uses the deployed API; set it to `http://localhost:8000` for a local backend (see `frontend/.env.example`).

## Docker (deploy)
```bash
docker build -t spherex-sky .
docker run -p 8000:8000 -v spherex-data:/data spherex-sky
```
Mount `/data` as a persistent disk so the cache survives restarts.

## Data credit
NASA/IPAC Infrared Science Archive (IRSA), SPHEREx Team. Based on IRSA SPHEREx tutorial notebooks (BSD-3-Clause).

## AI usage
Parts of the code were written with the help of an AI assistant (Claude). Marked in file headers.
