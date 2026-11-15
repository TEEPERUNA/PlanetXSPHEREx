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

### Flags
- Science writes a `FLAGS` layer (int32) into `pixels/<band>/epochN.fits`, and `flag_bits` (name → bit) plus `flag_bad` (names counted as unreliable) into `meta.json`. Bits are read from each SPHEREx image's FLAGS header (`MSKNnnnn` keys); `lib/flags.ts` holds the DR1 table as a fallback.
- The cursor info shows the flag names on the pixel; unreliable ones are amber, and each name has a plain-language tooltip.
- "x % flagged" under the date comes from `epochs[].detectors[band].flagged_frac` (ALL averages the detectors). It is only shown when `meta.flag_bits` exists, because older results counted every flag (SOURCE alone covers almost every pixel in dense fields).

## AI usage
Parts of this code were written with the help of an AI assistant (Claude).
