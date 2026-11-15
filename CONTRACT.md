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

Optional: `fov=<arcmin>` (default 3, max 20).

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
  "inverted": false,                          // true when negative-contrast mode is active (e.g. WISE 0855)
  "glare_suppressed": false,                  // true when primary star halo unsharp masking is active (e.g. Epsilon Indi B)
  "epochs": [
    {"index": 0, "date": "2025-05-06", "mjd_mean": 60801.0, "n_images": 18,
     "detectors": {"D1": {"n_images": 3, "flagged_frac": 0.02}, ...}}
  ],
  "outputs": {                                // per band + "ALL" (all detectors combined)
    "ALL": {
      "frames": ["frames/ALL/epoch0.png", "frames/ALL/epoch1.png"],
      "fits": ["epoch0_ALL.fits", "epoch1_ALL.fits"], // raw calibrated float32 FITS stacks
      "gif": "blink_ALL.gif",
      "diff": "diff_ALL.png"
    },
    "D1": {
      "frames": ["frames/D1/epoch0.png", "frames/D1/epoch1.png"],
      "fits": ["epoch0_D1.fits", "epoch1_D1.fits"],
      "pixels": ["pixels/D1/epoch0.fits", "pixels/D1/epoch1.fits"], // multi-layer pixel cubes
      "gif": "blink_D1.gif",
      "diff": "diff_D1.png"
    }
  },
  "spectrum": "spectrum.csv",
  "lightcurve": "lightcurve.csv",
  "lightcurve_png": "lightcurve.png",
  "light_curve": {                            // band-by-band variability analysis
    "is_variable": false,
    "variable_bands": [],
    "bands": {
      "D1": {"is_variable": false, "n_points": 5, "min_flux": 288.7, "max_flux": 616.2},
      ...
    },
    "points": [
      {"epoch": 0, "date": "2025-08-25", "mjd": 60916.08, "band": "D1", "flux": 486.29, "err": 0.95}, ...
    ]
  },
  "gaia_validation": {
    "status": "CONFIRMED_MATCH",              // "CONFIRMED_MATCH" | "VALIDATED_NON_GAIA" | "NO_GAIA_MATCH"
    "gaia_dr3_source_id": 4472832130942575872, // or null (e.g. wise0855 optical invisible)
    "target": "Barnard's Star",
    "target_key": "barnard",
    "message": "Vahvistettu Gaia DR3 -kohde (Barnard's Star). Ominaisliike projisoitu epookista J2016.0 vuoteen 2026.65.",
    "reference_epoch": "J2016.0",
    "target_epoch": 2026.65,
    "predicted_ra": 269.446124,
    "predicted_dec": 4.770075,
    "pixel_coords": {                         // calculated pixel coordinates in image
      "canvas_x": 15.0,                       // top-left origin (for HTML5 Canvas)
      "canvas_y": 15.0,
      "wcs_x": 15.0,                          // bottom-left origin (FITS standard)
      "wcs_y": 15.0
    },
    "pmra_masyr": -801.551,
    "pmdec_masyr": 10362.394,
    "parallax_mas": 547.45,
    "phot_g_mean_mag": 8.19,
    "accumulated_shift_arcsec": 110.69,
    "residual_offset_arcsec": 2.279,
    "is_match": true
  },
  "pmra_masyr": -801.6, "pmdec_masyr": 10362.4, // only for named targets
  "propagated_to": 2026.87,                   // decimal year to which target position was propagated
  "versions": ["7.0.5"], "generated": "...",
  "credit": "NASA/IPAC Infrared Science Archive (IRSA), SPHEREx Team"
}
```

All paths in `outputs`, `spectrum`, and `lightcurve` are relative to `base_url`.

Images: PNG, north up, east left, red crosshair at centre, same stretch for all epochs of a band.
`diff_*.png`: last epoch minus first, grey = no change, white = brighter now, black = fainter now.
Clean PNG frames are provided without hardcoded overlays; the viewer renders dynamic overlays (e.g. Gaia circle, crosshair toggle) client-side on Canvas using `pixel_coords`.

## `spectrum.csv`
`mjd, epoch, detector, wavelength_um, flux_mjy_sr, err_mjy_sr, flagged_frac`
One row per SPHEREx image, measured at the target's physical position at that epoch (3×3 px). Group by `epoch` to compare epochs (variable stars).

## `lightcurve.csv`
`epoch, date, mjd, band, flux_mjy_sr, err_mjy_sr`
Multi-epoch time-series photometric measurements grouped strictly by detector band (D1–D6). Avoids band-mixing artifacts across epochs with partial detector coverage.

## FITS files (`outputs[band].fits`)
Raw scientific calibrated float32 FITS images (`epoch{e}_{band}.fits`, `epoch{e}_ALL.fits`) registered to the tangent plane with standard WCS headers. Available via `/api/files/{job}/epoch{e}_{band}.fits`.

## Multi-Layer Pixel Cubes (`outputs[band].pixels`)
Available per epoch and detector band D1–D6 via `/api/files/{job}/pixels/{band}/epoch{e}.fits`.
Multi-Extension FITS (MEF) cubes registered onto the same 31×31 tangent-plane grid (same WCS as the stacks and PNGs), containing 7 float32 layers (accessible by extension name `EXTNAME`):
- `SB`: Surface Brightness (`IMAGE - ZODI`, MJy/sr), identical to the epoch stack.
- `ZODI`: Model zodiacal light foreground (MJy/sr).
- `SNR`: Signal-to-noise ratio per pixel (`SB / \sqrt{VARIANCE}`).
- `WAVE`: Central wavelength in $\mu\text{m}$ per pixel (from spectral WCS "W").
- `BW`: Bandpass bandwidth in $\mu\text{m}$ per pixel (from spectral WCS "W").
- `DETX`: Physical detector pixel X coordinate (0–2039) on the SPHEREx focal plane array.
- `DETY`: Physical detector pixel Y coordinate (0–2039) on the SPHEREx focal plane array.

## Rules
- Science (`science/`) may add new keys to `meta.json`, but must not rename or remove existing keys.
- Frontend must ignore unknown keys.
- New outputs (e.g. raw float frames, Gaia positions) are added as new keys and announced to the team.
