# Frontend – technical handoff

Folder: `frontend/` · Owners: Juho (app shell, search, styling), Elias (image viewer) · NASA Space Apps 2026

STARx Viewer is a public web tool. You enter a sky position (RA/Dec or a preset challenge target), and it shows every SPHEREx image of that patch as a short blink animation, so moving or changing objects stand out. It works on desktop and mobile.

This file covers the whole frontend. The image viewer has its own, more detailed handoff: [src/viewer/HANDOFF.md](src/viewer/HANDOFF.md).

Related docs: [CONTRACT.md](../CONTRACT.md) (API and data format), [STRUCTURE.md](../STRUCTURE.md) (whole repo).

## Quick start

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run build      # tsc --noEmit (strict) + vite build → dist/
```

- **Backend address:** `VITE_API_BASE_URL`. Without it the app uses the deployed Cloud Run API (`https://planetx-api-38053485414.us-east4.run.app`, set in `src/api/index.ts`). For a local backend, copy `.env.example` to `.env` (`http://localhost:8000`).
- **On a phone:** `npm run dev -- --host` and open the printed `Network:` address on the same Wi-Fi. Or use browser device mode (`Cmd+Opt+I`, then `Cmd+Shift+M`).
- **Hosting:** `dist/` is a static site that can be served from any static host. No frontend hosting is set up in this repo; the Dockerfile builds only the backend.

## Technology

| Part | Choice |
|---|---|
| Framework | React 19 + TypeScript 7 (strict), Vite 8 |
| Dependencies | `react`, `react-dom` only. No router, state library, UI kit or chart library |
| State | `useState` + one custom hook (`useSky`) |
| Styling | Plain CSS with custom properties, two files (`app.css`, `viewer.css`) |
| Fonts | Inter (UI) and JetBrains Mono (numbers), from Google Fonts in `index.html` |
| Tests | No test runner. `npm run build` is the check |

## Files

```
frontend/
├── index.html              title, meta description, theme-color, Google Fonts
├── .env.example            optional VITE_API_BASE_URL
└── src/
    ├── main.tsx            mounts <App />
    ├── state.ts            useSky(): search, polling, retry, backend notes; URL ↔ search
    ├── api/index.ts        the only file that knows the API address; types for responses
    ├── app/
    │   ├── App.tsx         page shell: top bar, search, banners, result card, mobile drawer
    │   ├── SearchForm.tsx  RA/Dec, field of view, preset targets
    │   ├── app.css         design tokens, buttons, form, layout, drawer, banners
    │   └── PLAN.md         original plan and requirements
    └── viewer/             image viewer (see src/viewer/HANDOFF.md)
        └── components/InfoPanels.tsx   "Controls info" and "Website info" dropdowns
```

**Rule:** `app/` imports the viewer only through `viewer/index.ts` (`Viewer`, `Meta`, `Result`, `ViewerStatus`). The viewer never calls the API and never imports from `app/`.

## Data flow

```
SearchForm ──onSearch(Search)──► useSky.setTarget
                                   │ writeUrl → ?target=… or ?ra=…&dec=…&fov=…
                                   │ GET /api/sky
                                   │ while not done: GET /api/status/<job> every 2 s
                                   ▼
                       status: ViewerStatus  ─► <Viewer status onRetry />
                       info: { fallback, note } ─► banner in App
```

### `api/index.ts`
- `getTargets()` → `/api/targets` (preset buttons). If it fails, the form still works without presets.
- `startSky(search)` → `/api/sky?target=…&fov=…` or `?ra=…&dec=…&fov=…`.
- `getStatus(job)` → `/api/status/<job>`.
- `fullUrl(base_url)`: the API returns a relative `base_url`; images need `API_BASE + base_url`.
- `SkyResponse` also has `precomputed`, `fallback` and `note`. They are optional because processing responses may omit them.
- Error bodies: `detail` from FastAPI becomes the error message.

### `state.ts` – `useSky()`
Returns `{ status, setTarget, retry, info }`.
- `setTarget(search)` aborts any running search (`AbortController`), writes the URL, and polls until `done` or `error`.
- **Polling is fault-tolerant:** up to 5 failed polls in a row are retried, because Cloud Run can go quiet while the job keeps running.
- While loading, `preview` (a quick result with fewer images) is passed to the viewer, which shows it with a progress bar.
- `retry()` runs the last search again. It is used by the "Try again" buttons.
- `info` is reset for each search and updated from every response. `note ?? previous`, so a note from a processing response survives to the end.
- `searchFromUrl()`: a shared link (`?target=barnard` or `?ra=…&dec=…&fov=…`) starts the search on page load.

### `SearchForm.tsx`
- RA/Dec accept degrees or sexagesimal (`08h55m10.8s`, `-7d14m42s`). The backend parses them.
- The field of view is 1–10 arcmin (default `DEFAULT_FOV = 3` in `state.ts`; backend max 10).
- **Preset targets:** picking one fills RA/Dec and marks it `active`. While a target is active, "Show sky" sends `{ target, fov }` (not coordinates), so the backend centres the moving star at today's position. Editing RA or Dec clears `active`. While a target is active, RA/Dec are not `required`, so a `?target=` link with empty fields can still be searched.

### `App.tsx`
- **Top bar:** logo mark and title. "Download GIF" appears once there is a result.
- **Download GIF:** the `download` attribute is ignored for other origins, so `saveGif` fetches the GIF and saves it from a blob URL. If the fetch fails, it opens the GIF in a new tab. This needs CORS on the GIF host (the API sends `Access-Control-Allow-Origin: *`).
- **Banners** (above the result):
  - `info.fallback === true`: yellow warning, "Live data unavailable – showing precomputed {fov}′ view", with the backend `note` under it and a "Try again" button. The FOV is computed from the shown image: `shape[1] × pixel_scale_arcsec / 60`.
  - Any other `note` (for example "Coordinates matched challenge target 'barnard'."): a small muted line.
- **Errors:** the viewer's error screen shows a "Try again" button (`onRetry`).
- **Layout:** see below.

## Layout and responsive behaviour

- **≥ 900 px:** two columns. The image is on the left, and the sidebar (`.viewer__side`: epoch info, cursor values, Gaia, controls, spectrum, credit, info dropdowns) is on the right, sticky, and scrolls on its own. The grid is set in `app.css` with `.app .viewer:has(.viewer__side)`.
- **< 900 px:** one column. The sidebar becomes a drawer that slides in from the right. A fixed "Controls" button opens it; the backdrop or `Esc` closes it (`open` state in `App.tsx`).
- The search form is on one row from 720 px and stacks below that. RA/Dec stack at 520 px or narrower.
- `prefers-reduced-motion` turns off the drawer slide, the button press and the dropdown chevron transitions.

## Design system

Dark only (`color-scheme: dark`). All tokens are in `:root` in `src/app/app.css`:

| Token | Value | Use |
|---|---|---|
| `--bg` / `--surface` / `--surface-2` | `#0a0b0d` / `#121418` / `#181b21` | page / cards / inputs and buttons |
| `--border` / `--border-strong` | `#24282f` / `#353a43` | hairlines / hover |
| `--text` / `--muted` | `#ece8e1` / `#8e939c` | text |
| `--accent` / `--accent-soft` / `--accent-text` | `#22d3ee` cyan / 12 % cyan / `#021216` | primary button, selected state, focus, sliders |
| `--danger` | `#ff6b6b` | error heading |
| `--radius` | `10px` | cards, image frame, banners |
| `--sans` / `--mono` | Inter / JetBrains Mono | UI / numbers and coordinates |

Fixed colours that are not tokens: Gaia ring `#22c55e` (science convention, in `viewer.css`), fallback warning `#fbbf24`, per-epoch spectrum colours (`epochColor` in the viewer).

**Buttons:**
- One style for the whole app (`.app button`): a ghost pill. `.primary` is solid cyan, and `[aria-pressed="true"]` is cyan-tinted.
- Hover changes the border and fill; `:active` presses down 1 px.
- Prev / Play / Next form one joined group (`.controls .controls__transport`). It needs the `.controls` prefix because `app.css` loads after `viewer.css` and would otherwise round every button.

**CSS load order:** `App.tsx` imports the viewer before `app.css`, so at equal specificity `app.css` wins. Keep this in mind when styling viewer elements.

## Accessibility

- All controls are real `<button>`, `<input>`, `<select>` or `<details>` elements with visible labels or `aria-label`. Toggles use `aria-pressed`, and the drawer button uses `aria-expanded`.
- Focus ring: 2 px cyan `:focus-visible`. Inside the joined transport group it is inset.
- Loading uses `role="status" aria-live="polite"`, and the error uses `role="alert"`.
- The info dropdowns use native `<details>/<summary>` with 44 px tap height.

## Known limits and open issues

- **No tests.** Logic worth testing first: `searchFromUrl`/`writeUrl`, the polling retry in `useSky`, and the viewer `lib/` functions.
- The **fallback banner** has not been seen live. It only appears when IRSA fails for a challenge target.
- `precomputed` is in the type but not shown anywhere.
- The **Download GIF** blob path relies on CORS on wherever the GIF is served from.
- **"Website info"** is only reachable once a result has loaded, because the sidebar does not exist before that.
- **Light mode** was removed in the restyle.
- Some "Integration" notes in `src/viewer/HANDOFF.md` are out of date. `App.tsx` no longer shows the GIF first, and `state.ts` now passes `preview` to the viewer.
- `src/viewer/msg_to_eliz.txt` and the Finnish `plan.md` files are working notes, not docs.

## AI usage
Parts of this code were written with the help of an AI assistant (Claude).
