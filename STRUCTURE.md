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
├── PROJECT_PLAN.md ........ requirements, UI ideas, FITS flag list
├── Dockerfile ............. runs the backend (uvicorn backend.main:app)
│
├── science/  (Emil)
│   ├── fetch_spherex.py ... MAIN SCRIPT
│   │     ← SIMBAD              target position + proper motion
│   │     ← IRSA (TAP + cutout) SPHEREx images
│   │     → gaia_validation.py  Gaia check
│   │     → output/<job>/       all output files (see examples/barnard)
│   ├── gaia_validation.py . hard-coded Gaia DR3 values for the 5 targets
│   ├── PLAN.md
│   └── requirements.txt
│
├── backend/  (Erik)
│   ├── main.py ............ FastAPI
│   │     → import fetch_spherex   runs the script as a job
│   │     → import fetch           fast image search + cutouts
│   │     /api/targets, /api/sky, /api/status/{job}
│   │     /api/files/*     ← output/     (real results)
│   │     /api/examples/*  ← examples/   (example data)
│   │     CORS: all origins allowed
│   ├── fetch.py ........... fast SPHEREx access: find_images, select, fetch_cutouts
│   ├── PLAN.md, SUBMISSION_backend.md
│   ├── s3_test.py ......... experiment: IRSA vs. S3 speed (not used by the API)
│   └── requirements.txt
│
├── output/<job>/ .......... created at runtime, not in git; same layout as examples/barnard
│
├── examples/barnard/ ...... one finished result for Barnard's Star
│   ├── meta.json .......... describes every other file (paths, epochs, bands)
│   ├── frames/<band>/epochN.png ... blink frames ───┐
│   ├── diff_<band>.png ............ difference ─────┤
│   ├── blink_<band>.gif ........... ready-made GIFs │  → App "Download GIF" link
│   ├── spectrum.csv ............... spectrum ───────┤
│   └── epochN_<band>.fits ......... raw float data  │  (not listed in meta.json yet)
│                                                    │
├── frontend/                                        │
│   ├── index.html, vite.config.ts                   │
│   ├── .env.example ... optional VITE_API_BASE_URL; default is the deployed API
│   └── src/                                         │
│       ├── app/  (Juho)                             │
│       │     App ......... layout: search on top, viewer image left, sidebar right (drawer + Controls button on mobile)
│       │     SearchForm .. RA/Dec, preset targets (fill RA/Dec), FOV
│       │     app.css ..... theme (dark, light via prefers-color-scheme), two-column layout, drawer; styles viewer buttons too
│       │     PLAN.md ..... copy of PROJECT_PLAN.md
│       │     → state.ts  setTarget(search)          │
│       ├── state.ts ......... shared: current search, URL sync, polling (useSky, retries failed polls)
│       ├── main.tsx ......... shared: mounts app/App
│       ├── api/  (shared)                           │
│       │     → backend /api/sky, /api/status        │
│       │     → Viewer as the `status` prop (preview sent as loading + preview)
│       └── viewer/  (Elias) ◄───────────────────────┘ /api/files/<job>/…
│           │     ← meta.gaia_validation (science/gaia_validation.py) for the Gaia circles
│           ├── index.ts ............ only entry point → Viewer, Meta, Result, ViewerStatus
│           ├── Viewer.tsx .......... picks empty/loading/preview/done; LoadedViewer owns the state
│           │     .viewer__side wraps everything below the image (app/ lays it out as the sidebar)
│           │     → components/*, hooks/useBlink, lib/frames, lib/gaia, viewer.css
│           ├── types.ts ............ Meta ≈ meta.json in CONTRACT.md (+ gaia_validation, detector ranges)
│           ├── viewer.css .......... all viewer styles (SVG overlay z-index keeps Gaia circles on top)
│           ├── components/
│           │   ├── BlinkImage.tsx ...... frames/*.png, diff_*.png + SVG overlay (31×31 px viewBox)
│           │   ├── EpochInfo.tsx ....... → lib/frames (imageCount)
│           │   ├── CursorInfo.tsx ...... → lib/skyCoords
│           │   ├── GaiaOverlay.tsx ..... → lib/gaia; circle on the epoch date + track dots
│           │   ├── GaiaInfo.tsx ........ → lib/gaia; line that explains the circle
│           │   ├── PlaybackControls.tsx  no dependencies
│           │   ├── SpectrumChart.tsx ... spectrum.csv → lib/parseSpectrum, lib/chartScale (SVG, no library)
│           │   └── StatusView.tsx ...... empty / loading / error + LoadingProgress → lib/stage
│           ├── hooks/useBlink.ts
│           ├── lib/ ......... pure functions, no React
│           │   ├── frames.ts      epochN.png → meta.epochs[N]
│           │   ├── skyCoords.ts   pixel ↔ RA/Dec
│           │   ├── gaia.ts        Gaia prediction moved to each epoch's date → pixel
│           │   ├── parseSpectrum.ts
│           │   ├── chartScale.ts  axes and scales for SpectrumChart
│           │   └── stage.ts       backend stage → text for the user
│           ├── HANDOFF.md ....... technical handoff: how the viewer works
│           ├── plan.md .......... working plan and open issues (Finnish)
│           └── msg_to_eliz.txt .. how to test the API by hand
```

## Rules
- `viewer/` and `app/` never import each other. They talk only through `state.ts` and `api/`.
- The frontend never calls IRSA, Gaia or SIMBAD directly. All data comes from the backend.
- `science/` may add new keys to `meta.json`, but never renames or removes them.

Update this file when you add, move or remove a file.
