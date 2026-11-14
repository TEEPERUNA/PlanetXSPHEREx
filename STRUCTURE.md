# Project structure

How the files in this repo relate to each other.
API and data formats: [CONTRACT.md](CONTRACT.md). Setup and running: [README.md](README.md).

Arrows: `←` reads from, `→` writes to or calls.
Images and FITS files are left out of the tree.

```
PlanetXSPHEREx/
│
├── CONTRACT.md ............ AGREEMENT: API + meta.json + spectrum.csv
│                            science writes it, backend serves it, frontend reads it
├── README.md .............. setup and running
├── STRUCTURE.md ........... this file
├── Dockerfile ............. runs the backend (uvicorn backend.main:app)
│
├── science/  (Emil)
│   ├── fetch_spherex.py ... MAIN SCRIPT
│   │     ← SIMBAD              target position + proper motion
│   │     ← IRSA (TAP + cutout) SPHEREx images
│   │     → gaia_validation.py  Gaia check
│   │     → output/<job>/       all output files (see examples/barnard)
│   ├── gaia_validation.py . hard-coded Gaia DR3 values for the 5 targets
│   ├── test_science.py .... tests for the two files above
│   └── requirements.txt
│
├── backend/  (Erik)
│   ├── main.py ............ FastAPI
│   │     → import fetch_spherex   runs the script as a job
│   │     /api/targets, /api/sky, /api/status/{job}
│   │     /api/files/*     ← output/     (real results)
│   │     /api/examples/*  ← examples/   (example data)
│   │     CORS: all origins allowed
│   ├── s3_test.py ......... experiment: IRSA vs. S3 speed (not used by the API)
│   └── requirements.txt
│
├── output/<job>/ .......... created at runtime, not in git; same layout as examples/barnard
│
├── examples/barnard/ ...... one finished result for Barnard's Star
│   ├── meta.json .......... describes every other file (paths, epochs, bands)
│   ├── frames/<band>/epochN.png ... blink frames ───┐
│   ├── diff_<band>.png ............ difference ─────┤
│   ├── blink_<band>.gif ........... ready-made GIFs │  (not used by the viewer yet)
│   ├── spectrum.csv ............... spectrum ───────┤
│   └── epochN_<band>.fits ......... raw float data  │  (not listed in meta.json yet)
│                                                    │
├── frontend/                                        │
│   ├── public/mock/barnard/ . copy of examples/barnard, so the viewer works without the backend
│   └── src/                                         │
│       ├── app/  (Juho)                             │
│       │     coordinate input, target list, URL     │
│       │     → state.ts  setTarget(ra, dec, fov)    │
│       ├── state.ts ......... shared (not created yet)
│       ├── main.ts .......... shared (not created yet)
│       ├── api/  (shared)                           │
│       │     → backend /api/sky, /api/status        │
│       │     → Viewer as the `status` prop          │
│       └── viewer/  (Elias) ◄───────────────────────┘ /api/files/<job>/…
│           ├── index.ts ............ only entry point → Viewer.tsx, types.ts
│           ├── Viewer.tsx .......... state; uses everything below
│           │     → components/*, hooks/useBlink, lib/frames, viewer.css
│           ├── types.ts ............ Meta ≈ meta.json in CONTRACT.md
│           ├── components/
│           │   ├── BlinkImage.tsx ...... frames/*.png, diff_*.png
│           │   ├── EpochInfo.tsx ....... → lib/frames (imageCount)
│           │   ├── CursorInfo.tsx ...... → lib/skyCoords
│           │   ├── PlaybackControls.tsx  no dependencies
│           │   ├── SpectrumChart.tsx ... spectrum.csv → lib/parseSpectrum
│           │   └── StatusView.tsx ...... empty / loading / error
│           ├── hooks/useBlink.ts
│           ├── lib/ ......... pure functions, no React
│           │   ├── frames.ts      epochN.png → meta.epochs[N]
│           │   ├── skyCoords.ts   pixel → RA/Dec
│           │   └── parseSpectrum.ts
│           └── plan.md
```

## Rules
- `viewer/` and `app/` never import each other. They talk only through `state.ts` and `api/`.
- The frontend never calls IRSA, Gaia or SIMBAD directly. All data comes from the backend.
- `science/` may add new keys to `meta.json`, but never renames or removes them.

Update this file when you add, move or remove a file.
