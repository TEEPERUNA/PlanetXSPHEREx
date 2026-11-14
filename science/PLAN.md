# Science & Image Processing Plan (`science/`)

**Owner:** Emil (Image Processing & Science Lead)  
**Project:** SPHEREx Sky – NASA Space Apps Challenge 2026 (Planet X and SPHEREx)  
**Architecture:** Python Science Engine feeding FastAPI Backend (`backend/`) and React Frontend (`frontend/`)

---

## 1. Domain & Scope Confirmation

The `science/` directory is **Emil's primary folder**. It encapsulates all scientific data acquisition, astrometric registration, image processing algorithms, spectrophotometric extraction, time-domain variability analysis, and ground-truth validation against external space catalogs (Gaia DR3 / CatWISE).

```
science/
├── fetch_spherex.py      # Core processing pipeline: IRSA TAP, cutouts, stacks, difference, spectra, light curves
├── gaia_validation.py    # Gaia DR3 query & proper motion propagation service (J2016.0 -> observation epoch)
├── test_science.py       # Comprehensive scientific test suite verifying all 5 challenge targets
├── requirements.txt      # Astronomy and image processing dependencies (Astropy, Photutils, Reproject, Scipy, etc.)
└── PLAN.md               # This master plan and roadmap
```

---

## 2. What Has Been Completed So Far (Done)

### A. Multi-Epoch Image Processing & Motion Visualization
- [x] **IRSA TAP Query Pipeline:** Built programmatic access to NASA/IPAC Infrared Science Archive querying `spherex.artifact` and `spherex.plane` tables for multi-epoch, multi-detector FITS cutouts.
- [x] **Astrometric Registration / Reprojection:** Implemented `reproject_one()` using `astropy.wcs.WCS` and `reproject_interp` onto a shared tangent-plane grid, ensuring pixel-to-pixel alignment across epochs separated by months/years.
- [x] **Astronomical Contrast Stretch:** 
  - Implemented dynamic stretch (`asinh` and `ZScaleInterval`) converting 32-bit floating-point astronomical fluxes to display-ready 8-bit PNG frames.
  - Added negative contrast mode (`invert=True`), replicating WiseView's inverted grayscale for spotting faint diffuse infrared sources.
- [x] **Difference Imaging ($\Delta I$):**
  - Implemented `diff_png()` computing $\Delta I = \text{Epoch}_{\text{last}} - \text{Epoch}_{\text{first}}$.
  - Zero-centered stretch (zero difference $\rightarrow$ neutral gray 127):
    - **Moving objects** (Barnard's Star, WISE 0855) produce a **dipole** (dark negative hole at initial location + bright positive peak at current location).
    - **Variable stars** (R Dra, RW Aur) produce a **monopole** (single bright or dark pulsating point source).
- [x] **Signal-to-Noise Stacking:** Implemented `robust_norm()` with MAD (Median Absolute Deviation) normalization and S/N-weighted co-adding across detectors into `epoch*_ALL.fits`.

### B. Special Astronomical Enhancements for Challenging Targets
- [x] **WISE 0855-0714 (Coldest known planetary-mass brown dwarf, $T \sim 250\text{ K}$):**
  - Stripped diffuse infrared foreground via Zodiacal light model subtraction (`IMAGE - ZODI`).
  - Automated inverted grayscale stretch (`invert=True`) so the moving sub-brown dwarf stands out against the background field.
  - Handled non-optical detection: recognized that WISE 0855 is invisible in optical Gaia G-band and validated against CatWISE2020 / unWISE astrometry ($8.16''/\text{year}$).
- [x] **Epsilon Indi B (Brown dwarf binary companion next to a magnitude ~4.7 primary star):**
  - Implemented `suppress_stellar_glare()` using spatial unsharp masking (Gaussian high-pass filter) to suppress the primary star's blinding diffraction halo and isolate the brown dwarf companion.
- [x] **Decoupling from Slug Names:** Implemented `identify_benchmark_target()` which identifies targets via name normalization and sky coordinate proximity ($<3.0'$). Eliminates bugs when API queries use custom fields of view (e.g. `epsindib_fov5`) or raw coordinates (`ra331.0438_dec-56.7827_fov5`).

### C. Spectroscopy & Time-Domain Light Curves
- [x] **102-Channel Near-Infrared Spectrophotometry (0.75–5.0 µm):**
  - Mapped pixel coordinates $(X, Y)$ to physical wavelengths ($\mu\text{m}$) using the `WCS-WAVE` spectral table.
  - Performed 3×3 aperture photometry with error propagation (`center_flux`, `center_err`).
  - Exported standardized `spectrum.csv` and multi-epoch overlay plot `spectrum.png`.
- [x] **Per-Band Multi-Epoch Light Curves:**
  - **Fixed band-mixing bug:** Restructured `plot_lightcurve()` to group measurements strictly per detector band (D1 through D6).
  - Evaluates photometric variability *only within the same band* across epochs.
  - Prevents false-positive variability for stable stars with unequal detector coverage (e.g., Barnard's Star having D1–D6 in Epoch 0, but only D1 and D4 in Epoch 1).
  - Exported `lightcurve.csv` (with `epoch, date, mjd, band, flux_mjy_sr, err_mjy_sr`), multi-band comparison plot `lightcurve.png`, and `"light_curve"` metadata in `meta.json`.

### D. Gaia DR3 Astrometric Validation
- [x] **Astrometric Propagation Service ([`gaia_validation.py`](file:///Users/emil/Documents/Projektit/NASA%20Space%20Apps/projekti/science/gaia_validation.py)):**
  - Extracted Gaia DR3 reference coordinates at epoch J2016.0 with proper motions ($\mu_\alpha^*, \mu_\delta$) and parallax.
  - Propagated celestial coordinates forward across $\sim 10$ years to the SPHEREx observation dates (2025–2026).
  - Quantified cumulative motion: Barnard's Star ($103.9''$), $\epsilon$ Indi B ($47.1''$), RW Aur ($0.18''$), R Dra ($0.15''$).
  - Appended `"gaia_validation"` block into `meta.json` and rendered green Gaia predicted position indicators on output PNG frames.

### E. Quality Assurance & Automated Testing
- [x] Built and verified [`science/test_science.py`](file:///Users/emil/Documents/Projektit/NASA%20Space%20Apps/projekti/science/test_science.py) testing:
  - Target resolution under varied FOV slugs and coordinate inputs.
  - Gaia validation for all 5 challenge benchmarks.
  - Glare suppression effectiveness.
  - Stability verification for Barnard's Star under unequal detector coverage.
  - Genuine variability detection for R Draconis and RW Aurigae.

---

## 3. What Still Needs to Be Done (Next Steps & Roadmap)

### Phase 1: Pre-computing Benchmark Data for the 5 Challenge Targets
* [ ] **Run and cache all 5 challenge targets locally:**
  Ensure the team has pre-fetched and generated complete data folders in `output/` (or `examples/`) so the hackathon live demo never hangs on internet / archive latency:
  ```bash
  python science/fetch_spherex.py --target barnard --per-group 3
  python science/fetch_spherex.py --target epsindib --per-group 3
  python science/fetch_spherex.py --target wise0855 --per-group 3
  python science/fetch_spherex.py --target rwaur --per-group 3
  python science/fetch_spherex.py --target rdra --per-group 3
  ```
* [ ] **Validate outputs:** Check that each target folder has:
  - `frames/` for each detector (D1–D6, ALL)
  - `diff_*.png` and `blink_*.gif`
  - `spectrum.csv` and `spectrum.png`
  - `lightcurve.csv` and `lightcurve.png`
  - `meta.json` containing complete `"light_curve"` and `"gaia_validation"` blocks.

### Phase 2: Frontend & Backend Integration Support
* [ ] **Hand-off to Erik (Backend):**
  - Verify that Erik's `backend/main.py` warmup routine seamlessly detects pre-computed folders.
  - Ensure API endpoints `/api/targets`, `/api/sky`, `/api/status`, and `/api/files` serve all science artifacts correctly.
* [ ] **Hand-off to Eliz (Image Viewer Frontend):**
  - Assist Eliz in reading `meta.json`:
    - Point her to `"outputs"` for the Canvas blink player and difference toggle.
    - Point her to `"spectrum"` (`spectrum.csv`) for rendering the interactive wavelength vs. flux chart.
    - Point her to `"light_curve"` (`lightcurve.csv` / JSON) for rendering the multi-band time-series light curve chart.
* [ ] **Hand-off to Juho (App, Aladin Lite & Gaia):**
  - Verify that Juho's Aladin Lite sky map and Gaia overlay align with the coordinates and proper motion values reported in `meta.json`.

### Phase 3: Pitch, Science Narrative & Documentation
* [ ] **Science Explanations for the Presentation Video (3 min):**
  - Prepare clear 1-paragraph explanations for judges:
    - *How does difference imaging reveal moving bodies (dipoles)?*
    - *Why is WISE 0855 only visible in mid-IR bands D5/D6 (4.5–5.0 µm)?*
    - *How does Gaia DR3 cross-matching separate true solar system candidates / high proper motion stars from stationary background noise?*
* [ ] **Documentation Polish:** Keep `CONTRACT.md` and `README.md` updated with any newly introduced metadata keys.

---

## 4. Benchmark Targets Quick Reference

| Key | Object | Coordinates (J2000) | Expected Motion / Science | Optimal Processing |
| :--- | :--- | :--- | :--- | :--- |
| `barnard` | **Barnard's Star** | `17h 57m 48.5s` `+04° 41′ 36″` | $\sim 10.39''/\text{yr}$ jump across epochs | Standard stretch, large dipole in $\Delta I$ |
| `epsindib` | **Epsilon Indi B** | `22h 04m 10.5s` `-56° 46′ 58″` | Brown dwarf companion sharing host star's motion | Unsharp masking / glare suppression |
| `wise0855` | **WISE 0855-0714** | `08h 55m 10.8s` `-07° 14′ 42″` | Coldest known Y-dwarf ($T \sim 250\text{ K}$), $\sim 8.16''/\text{yr}$ | Bands D5/D6, ZODI subtraction, negative invert |
| `rwaur` | **RW Aurigae** | `05h 07m 49.5s` `+30° 24′ 05″` | Eruptive T Tauri star with circumstellar dust dips | NIR excess spectrum, multi-band light curve dips |
| `rdra` | **R Draconis** | `16h 32m 40.2s` `+66° 45′ 18″` | Mira variable ($P \approx 245.6\text{ d}$), deep molecular absorption | Water/CO band spectrum, periodic light curve |
