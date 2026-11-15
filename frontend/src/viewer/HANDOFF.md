# Image Viewer – technical handoff

Owner: Elias · Folder: `frontend/src/viewer/` · Status: feature-complete for NASA Space Apps 2026

The viewer shows the SPHEREx images of one sky position as a blink animation between epochs, so moving or changing objects stand out. It also shows a difference image, the coordinates under the cursor, the spectrum, and the predicted Gaia position.

Related docs: [CONTRACT.md](../../../CONTRACT.md) (API and data format), [STRUCTURE.md](../../../STRUCTURE.md) (whole repo), [plan.md](plan.md) (Finnish working plan, open issues).

## Technology

| Part | Choice | Why |
|---|---|---|
| Framework | React 19 + TypeScript, built with Vite (set up by Juho in `frontend/`) | Team standard |
| Images | Plain `<img>` + CSS `image-rendering: pixelated` | PNGs come ready from science; no canvas needed |
| Overlay | Inline SVG, `viewBox="0 0 31 31"` = SPHEREx pixels | Circles stay sharp at any size |
| Brightness / contrast | CSS `filter` | No pixel processing needed |
| Spectrum chart | Hand-drawn SVG | No chart library, so no new dependencies |
| State | React `useState` in one component | Nothing else needs it |

**The viewer adds no npm packages.** It only uses React.

## How it plugs in

The app imports only `index.ts`:

```tsx
import { Viewer, type ViewerStatus } from "../viewer";

<Viewer status={status} />
```

`status` is the only prop:

```ts
type ViewerStatus =
  | { kind: "empty" }
  | { kind: "loading"; stage: string; done: number; total: number; preview?: { meta: Meta; baseUrl: string } }
  | { kind: "done"; meta: Meta; baseUrl: string }
  | { kind: "error"; message: string };
```

Rules for the caller (`state.ts` / `api/`):
- `meta` is the `meta.json` object from `/api/sky` or `/api/status`, passed as is.
- `baseUrl` must be the **full** address: `API_BASE + base_url`. The API returns a relative path.
- `stage` is passed as is, including the `preview_` prefix. The viewer turns it into readable text.
- `preview` is optional. When it is set, the viewer shows the quick preview with a progress bar above it.

The viewer never calls the API and never imports from `app/`. It only fetches the files that `meta.json` points to (PNGs and `spectrum.csv`).

## Files

```
viewer/
├── index.ts              public exports: Viewer, Meta, Result, ViewerStatus
├── Viewer.tsx            picks the state to show; LoadedViewer owns all viewer state
├── types.ts              Meta (subset of meta.json), ViewerStatus, Frame, Pixel
├── viewer.css            all styles, class names start with the component name
├── components/
│   ├── BlinkImage.tsx        image stack + SVG overlay + pointer → pixel
│   ├── EpochInfo.tsx         "Epoch 2/4 · 2026-03-16 · 10 images"
│   ├── CursorInfo.tsx        pixel, RA, Dec under the cursor or last tap
│   ├── GaiaOverlay.tsx       green circle + track dots (SVG)
│   ├── GaiaInfo.tsx          text line that explains the circle
│   ├── PlaybackControls.tsx  band, play/pause/step, speed, diff, Gaia, brightness, contrast
│   ├── SpectrumChart.tsx     loads spectrum.csv and draws it
│   └── StatusView.tsx        empty / loading / error, and LoadingProgress
├── hooks/
│   ├── useBlink.ts           interval timer for the animation
│   └── usePixelValues.ts     loads the pixel FITS for the cursor info, hides filler layers
└── lib/                      pure functions, no React, easy to test
    ├── frames.ts             frames of a band; epoch number from the filename
    ├── skyCoords.ts          pixel ↔ RA/Dec
    ├── gaia.ts               Gaia prediction moved to each epoch's date
    ├── parseSpectrum.ts      spectrum.csv → rows
    ├── chartScale.ts         axis ranges and ticks for the chart
    ├── spectrumStats.ts      averages per detector, noise check
    ├── fits.ts               small FITS reader (pixel values under the cursor)
    ├── flags.ts              SPHEREx flag bits → names, unreliable or not, tooltip text
    └── stage.ts              backend stage name → user text
```

## How the main parts work

### Blink
- `framesFor(meta, band, baseUrl)` lists the band's PNGs. **The epoch comes from the filename** (`epoch3.png` → `meta.epochs` entry with `index: 3`), never from list position, because bands have different epoch sets.
- All frames of the band are in the DOM at once, stacked in one CSS grid cell. Only one has `visibility: visible`. Switching frames never waits for a download.
- `useBlink(playing, fps, onTick)` runs a `setInterval`. Stepping by hand pauses playback.

### Compare two dates
"Compare two dates" turns the blink into a classic blink comparator: it alternates only between date A and date B (defaults: first and last). A and B are stored as dates (`compareA`, `compareB`, mjd) and resolved with `nearestFrame()`, so they survive band changes and the preview → full switch. Internally `playFrames` is the played list (all frames, or just A and B); `playIdx` is the position in it and `idx` the position in the full list used by the image stack and the info lines. Not available in diff mode.

### Keeping state between results
`LoadedViewer` gets `key = target|shape` (the target name is unique per search, the shape changes with the field of view). The preview and the full result of the same search share the key, so band, date and sliders survive the switch. A new search gets a new key, and React starts the component fresh. The exact RA/Dec is not part of the key, because a moving star's position can differ slightly between runs.

The viewer remembers the **date** on screen (`anchorMjd`), not a position in the frame list. The preview usually has fewer epochs than the full result, so a list position would point at another date. `nearestFrame()` picks the frame closest to the remembered date; this also keeps the date when the band changes. If the new result lacks the selected band, the first band is used (`activeBand`).

The spectrum keeps the old chart on screen until the new CSV has loaded, so the page does not jump.

### Coordinates
`pixelToSky` and `skyToPixel` use a flat-sky approximation around the image centre. North is up and east is left, so RA grows to the left. Whole numbers are pixel centres; (15, 15) is the centre of a 31 × 31 image. Checked against the FITS WCS headers: centre and orientation match, and the error at the edge is far below a pixel.

### Gaia circles
- Input: `meta.gaia_validation` (`predicted_ra/dec` at `target_epoch`, plus proper motion).
- For every epoch the position is moved to that epoch's date (`mjd_mean`) and converted to a pixel. The result matches science's own `pixel_coords` to 0.01 px.
- In blink mode a circle marks the current date, and dots show the track. In diff mode, dashed = first epoch and solid = last epoch.
- SVG pixel *i* spans *i* … *i*+1, so circles are drawn at *x* + 0.5.
- The SVG layer has `position: relative; z-index: 1`. **Do not remove it:** images with a CSS `filter` get their own layer and would otherwise paint over the circles.

### Spectrum
- One measurement per SPHEREx image, at the image centre (3 × 3 px). x = wavelength (µm), y = surface brightness (MJy/sr), with error bars, one colour per epoch.
- Default view "Average per detector" (`lib/spectrumStats.ts`): one point per detector and date (mean, error of the mean), joined by a line, so the shape and any change between dates are easy to see. "All measurements" shows every point.
- A plain-language intro sits above the chart, with hints under the x axis. A warning appears when at least 60 % of points are within 2σ of zero.
- Detector ranges D1–D6 are shaded in the background.
- The epoch on screen in the blink is highlighted and the others are dimmed, so brightness changes between epochs are easy to see.
- The x axis is fitted to the data (about 0.75–5 µm). The y axis starts at 0 unless flux goes below it. Checked against all five challenge targets: every point fits.

### Loading
`describeStage` maps `queued`, `downloading`, `processing` to text and strips the `preview_` prefix. The bar shows a count only while `done < total`. When the backend sits at `processing 36/36` for minutes, the bar is indeterminate instead of stuck at full.

## Flags (contamination and quality)

SPHEREx marks every pixel of every image with bit flags: saturated, hit by a cosmic ray, dead, afterglow, and so on. The challenge asks for "metadata, like contamination flags", so the viewer shows them in two places:

- **Under the cursor:** `Flags: OVERFLOW, SOURCE`. Unreliable flags are amber and listed first; every name has a plain-language tooltip. `Flags: none` means the pixel is clean.
- **Under the date:** `· 2.5 % flagged`, the share of unreliable pixels in that image.

### What the flags mean

The names and bits come from the FLAGS header of a real SPHEREx DR1 image (`MSKNnnnn` = name of plane nnnn, `MSKDnnnn` = description). "Unreliable" is the list science counts in `flagged_frac` (`BAD_FLAGS`).

| Bit | Name | Meaning | Unreliable |
|---|---|---|---|
| 0 | TRANSIENT | Cosmic-ray hit or other short event during the exposure | yes |
| 1 | OVERFLOW | Saturated: the source was too bright (the cause of the "donuts") | yes |
| 2 | SUR_ERROR | Error in onboard processing | yes |
| 6 | NONFUNC | Permanently unusable pixel | yes |
| 7 | DICHROIC | Low efficiency due to the dichroic beam splitter | yes |
| 9 | MISSING_DATA | Onboard data lost | yes |
| 10 | HOT | Hot pixel | yes |
| 11 | COLD | Anomalously low signal | yes |
| 12 | FULLSAMPLE | Full sample history is available | no, information |
| 14 | PHANMISS | Phantom correction was not applied | no |
| 15 | NONLINEAR | Nonlinearity correction cannot be applied reliably | yes |
| 17 | PERSIST | Afterglow from a bright source in an earlier exposure | yes |
| 19 | OUTLIER | Flagged as an outlier | yes |
| 20 | CROSSTALK | Echo of a bright source elsewhere on the detector | no, warning |
| 21 | SOURCE | A known source is at this pixel | no, information |
| 22 | GHOST | Reflection of a bright source in this exposure | no, warning |
| 23 | GHOST_FPA | Reflection of a bright source on another detector | no, warning |
| 24 | GHOST_EXT | Reflection of a bright source outside the field of view | no, warning |
| 25 | STREAK | Affected by a streak | no, warning |
| 26 | BLOOM | Charge spilled over from a saturated pixel | yes |
| 27 | SNOWBALL | Part of a large cosmic-ray "snowball" event | yes |
| 28 | HALO | Part of a glow around a bright transient | no, warning |

SOURCE alone covers almost every pixel in dense fields (99 % of one full Milky Way image), so it must never count as a problem.

### How it is implemented

**Science (`science/fetch_spherex.py`)**
1. `FLAG_BITS` is the DR1 table above (name → bit). `BAD_FLAGS` lists the unreliable names, and `bad_mask(bits)` turns them into a bitmask. `BAD_PIXEL_MASK = bad_mask(FLAG_BITS)`.
2. `read_flag_bits(header)` reads the `MSKNnnnn` keys of each image's FLAGS header, so a later data release with a different layout still decodes correctly. With no keys it returns `FLAG_BITS`.
3. `parse_cutout_hdul` stores `c.flag_bits` and `c.bad_mask` on each `Cutout`, and computes `flagged_frac` with the image's own mask. `--mask-flags` uses the same mask.
4. `build_pixel_cube` writes an 8th layer, `FLAGS` (int32), into `pixels/<band>/epochN.fits`. It takes the flags of the **representative image** (the same one used for wavelength and detector pixel) at the **nearest pixel**, because bits cannot be interpolated. The plane names go into the layer header as `MSKNnnnn`. The layer is only written when the image could be mapped onto the 31×31 grid.
5. `meta.json` gets `flag_bits` (name → bit, from the first image) and `flag_bad` (`BAD_FLAGS`).

**Viewer**
1. `types.ts`: `Meta.flag_bits`, `Meta.flag_bad`, and `flagged_frac` in `epochs[].detectors`.
2. `hooks/usePixelValues.ts` reads the `FLAGS` layer like the other layers. `FLAGS` is in `ALWAYS_KEEP`: a layer that is the same everywhere is normally treated as filler and hidden, but "no flags anywhere" is real data.
3. `lib/flags.ts`: `decodeFlags(value, bits, bad)` turns the integer into names, unreliable first. It falls back to the DR1 table (`DR1_FLAG_BITS`, `DR1_BAD_FLAGS`) when `meta.json` has no `flag_bits`. `FLAG_TEXT` holds the tooltip texts.
4. `components/CursorInfo.tsx` shows the names as `<abbr>` with the tooltip; `.viewer__flag.is-bad` makes unreliable ones amber.
5. `lib/frames.ts` `flaggedFraction(epoch, band)` gives the share for one band, or the average over the detectors for ALL. `components/EpochInfo.tsx` shows it **only when `meta.flag_bits` exists**: results made before this change counted every set bit, including SOURCE, and showed 20–100 %.

### Bugs this fixed in science
- The old bad-pixel mask had three wrong bits: "OUTLIER" at 20 (really CROSSTALK), "BLOOM" at 27 (really SNOWBALL), and an extra bit 28 (HALO).
- Old results counted every set bit (`flags != 0`), so `flagged_frac` was 0.2–1.0. On a real DR1 cutout the old way gives 27.1 % and the new way 2.5 %.

### Checked
- Science tests, including the new `test_read_flag_bits` and the FLAGS checks in `test_multi_layer_pixel_cube`. On Windows, `test_gaia_timeout_and_skip_flag` (timing) and the temp-folder cleanup of `test_multi_layer_pixel_cube` (file lock) fail the same way with the code from before this change; the pixel-cube assertions pass with `fits.conf.use_memmap = False`.
- End to end with real data: one DR1 image read from S3 with `backend/fetch.py` → `parse_cutout_hdul` → `build_pixel_cube` → read back with the viewer's `readFits` and `decodeFlags`. In that 31×31 patch, 649 pixels had no flags, about 290 only informational ones, and about 20 unreliable ones.

### Limits
- Flags come from one representative image per epoch and band, not from every image in the stack.
- ALL has no pixel cube, so no flags under the cursor; its "% flagged" is the average of the detectors.
- The precomputed `examples/` were rebuilt without the original images, so they have no flags. New searches have them.
- CONTRACT.md does not list `flag_bits`, `flag_bad` or the `FLAGS` layer yet.

## Testing

No test runner is set up. What has been checked:
- `npm run build` in `frontend/` (TypeScript strict + Vite build) passes.
- The `lib/` functions were run against the live API for all 5 targets, a free coordinate (M31) and bad input: frames, epochs, centre coordinates, spectrum rows, chart axes and Gaia pixels.

To try the viewer: in `frontend/`, put `VITE_API_BASE_URL=https://planetx-api-38053485414.us-east4.run.app` in `.env` (UTF-8), then `npm run dev`.

## Known limits and open issues

Data issues (science side, see [plan.md](plan.md) section 8):
- Gaia predictions are off for Barnard's Star (172″, outside the image) and Epsilon Indi B (78″). The viewer says so in the info line instead of hiding it.
- The Gaia lookup for free coordinates fails (`name 'cf' is not defined`), so free coordinates show no circle.
- The spectrum is measured at a fixed centre, so a fast-moving star is under-measured in early epochs.
- WISE 0855 images are inverted (negative), and `meta.json` does not say so yet.

Integration (app side):
- `App.tsx` shows the backend GIF first and the viewer behind "Show frame-by-frame".
- `state.ts` sends the preview as `kind: "done"` and does not use the `preview` field.
- Target name and credit appear in both the app and the viewer.

Not built: light curve (`lightcurve.csv`), free difference or sum of any two epochs (needs computing from the FITS stacks), zoom.

## AI usage
Parts of this code were written with the help of an AI assistant (Claude).
