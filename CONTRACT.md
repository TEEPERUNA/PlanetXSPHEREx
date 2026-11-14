# API & Data Contract

This file is the agreement between backend, science and frontend.
**Don't change it without telling the team.**

Base URL: `http://localhost:8000` locally, deployed URL later. The frontend uses one `API_BASE_URL` setting.

## Endpoints

### `GET /api/targets`
The 5 challenge targets.
```json
[{"key": "barnard", "label": "Barnard's Star", "ra": 269.45, "dec": 4.69, "cached": true}, ...]
```
Keys: `barnard`, `epsindib`, `wise0855`, `rwaur`, `rdra`.

### `GET /api/sky`
Query params, use one of these:
- `target=<key>` (from `/api/targets`)
- `ra=<deg or 08h55m10.8s>&dec=<deg or -7d14m42s>`

Optional: `fov=<arcmin>` (default 3, max 10).

Responses:
```json
// already cached → instant
{"status": "done", "job": "barnard", "base_url": "/api/files/barnard/", "meta": { ...meta.json... }}

// not cached → job started, poll /api/status/<job>
{"status": "queued", "job": "ra133.7950_dec-7.2450_fov3"}
```
Errors: `400` bad input, `404` unknown target.

### `GET /api/status/{job}`
Poll every ~2 s until `status` is `done` or `error`.
```json
{"job": "...", "status": "processing", "stage": "downloading", "done": 23, "total": 47, "error": null}
{"job": "...", "status": "done", "base_url": "/api/files/<job>/", "meta": { ... }}
{"job": "...", "status": "error", "error": "No SPHEREx images cover this position"}
```
`stage` is one of `queued`, `preview_downloading`, `preview_processing`, `downloading`, `processing`, `done`.

**Quick preview:** for new coordinates the backend first does a fast run (1 image per epoch+detector).
When it's ready, status includes a `preview` object. Show it right away, then swap to the full result when `status` is `done`:
```json
{"job": "...", "status": "processing", "stage": "downloading", "done": 5, "total": 54,
 "preview": {"base_url": "/api/files/<job>__preview/", "meta": { ... }}}
```
`preview` is `null` until the quick run is finished.

### `GET /api/files/{job}/{path}` and `GET /api/examples/{job}/{path}`
Static files listed in `meta.json`, e.g. `/api/files/barnard/frames/ALL/epoch0.png`.
**Always use the `base_url` the API returns**: results precomputed in the repo's `examples/` folder are served from `/api/examples/`.

## `meta.json`

```jsonc
{
  "target": "Barnard's Star",
  "ra_deg": 269.45, "dec_deg": 4.77,          // image centre (proper motion applied to today)
  "fov_arcmin": 3, "pixel_scale_arcsec": 6.15,
  "shape": [31, 31],                          // pixels (height, width)
  "bands": ["D1","D2","D3","D4","D5","D6"],
  "detector_ranges_um": {"D1": [0.75, 1.09], ...},
  "epochs": [
    {"index": 0, "date": "2025-05-06", "mjd_mean": 60801.0, "n_images": 18,
     "detectors": {"D1": {"n_images": 3, "flagged_frac": 0.02}, ...}}
  ],
  "outputs": {                                // per band + "ALL" (all detectors combined)
    "ALL": {"frames": ["frames/ALL/epoch0.png", "frames/ALL/epoch1.png"],
            "gif": "blink_ALL.gif", "diff": "diff_ALL.png"},
    "D1": { ... }
  },
  "spectrum": "spectrum.csv",
  "pmra_masyr": -801.6, "pmdec_masyr": 10362.4, // only for named targets
  "versions": ["..."], "generated": "...",
  "credit": "NASA/IPAC Infrared Science Archive (IRSA), SPHEREx Team"
}
```

All paths in `outputs` and `spectrum` are relative to `base_url`.

Images: PNG, north up, east left, red crosshair at centre, same stretch for all epochs of a band.
`diff_*.png`: last epoch minus first, grey = no change, white = brighter now, black = fainter now.

## `spectrum.csv`
`mjd, epoch, detector, wavelength_um, flux_mjy_sr, err_mjy_sr, flagged_frac`
One row per SPHEREx image, measured at the centre (3×3 px). Group by `epoch` to compare epochs (variable stars).

## Rules
- Science (`science/`) may add new keys to `meta.json`, but must not rename or remove existing keys.
- Frontend must ignore unknown keys.
- New outputs (e.g. raw float frames, Gaia positions) are added as new keys and announced to the team.
