# Submission texts – backend part (Erik)

Copy these into the Space Apps project page. All text is in English, as required.
Numbers below are measured in our own tests; update them if they change.

---

## Detailed Project Description – "How does it work?" (backend)

**Data pipeline and API**

Behind the web tool is a Python backend (FastAPI) running on Google Cloud Run. When a user enters sky coordinates (RA/Dec) and a field of view, or picks one of the challenge targets:

1. **Search** – The backend asks NASA/IPAC's Infrared Science Archive (IRSA) which SPHEREx spectral images cover that position (IVOA SIA service). It uses the newest data release available (Data Release 1, falling back to Quick Release 3).
2. **Download** – Instead of downloading full 2040×2040-pixel detector images (tens of MB each), the backend reads only the small patch of pixels it needs, directly from the official SPHEREx copy on Amazon S3 (`s3://nasa-irsa-spherex`, part of the AWS Open Data program). It reads the image, flags, variance and zodiacal-light layers for up to 32 files in parallel and rebuilds a correct sky coordinate system (WCS) for each patch.
   - We verified that the S3 data is bit-for-bit identical to IRSA's files (same processing version, identical pixels).
   - In our tests this cut download time for a typical target from 90–136 s with frequent server errors to about 10–20 s with no errors.
3. **Processing** – The science module subtracts the zodiacal light, groups the images into survey epochs (SPHEREx maps the whole sky every ~6 months), stacks them per detector band, and renders the blink frames, difference images and spectrum (see the science section).
4. **Results** – The frontend receives a JSON description (`meta.json`) with links to every frame, and plays them as an animation.

**Speed and freshness**

- **Quick preview:** for new coordinates the backend first produces a fast preview (one image per epoch and band) so users see the sky within seconds, then replaces it with the full-quality result.
- **Cache:** finished results are stored in Google Cloud Storage. The five challenge targets (Barnard's Star, Epsilon Indi B, WISE 0855, RW Aurigae, R Draconis) are prepared at startup and open instantly.
- **Always up to date:** each cached result records which data release and how many images it used. At most once a day the backend checks IRSA for new SPHEREx observations and rebuilds the result only if new data exists, so the tool keeps up with SPHEREx's growing archive without manual work.
- **Embeddable:** every view can be opened directly from a URL with coordinates, and the API is open (CORS enabled) so other websites and projects can use it.

**Discovery tools**

- **Community candidate reports:** anyone who spots a moving or unusual object can click it and report it. Reports are stored centrally, shown as markers to every later visitor of the same field, and grouped: the tool tells the user how many others reported the same spot and warns when it is simply a known challenge target. This turns the viewer into a small citizen-science platform for the Planet X search, and it keeps working even when the SPHEREx archive is busy.
- **Gaia field stars:** the backend fetches every ESA Gaia DR3 star around the image (positions and proper motions) so the viewer can mark known stars at each SPHEREx epoch. Anything moving that Gaia does not know about stands out. The catalogue is queried from several VizieR mirrors with short timeouts and cached permanently, because Gaia DR3 never changes.
- **Data-quality control:** users can ask for images with flagged pixels (cosmic rays, saturation, hot and dead pixels, persistence…) left out of the stacks, using the SPHEREx Level 2 quality flags, so artefacts are not mistaken for new objects.
- **Fields of view up to 20 arcmin**, so faster-moving objects can be followed between epochs.

**Built to stay up during judging**

- The five challenge targets are bundled precomputed in the server image and are shown with a clear notice if live data is unavailable.
- Background updates are swapped in atomically, so users never see half-written results.
- Simple per-user rate limits and a queue limit keep the single server responsive.
- Every change is built automatically in GitHub Actions before deployment, and library versions are pinned.

**Tools and languages (backend):** Python, FastAPI, Astropy, Astroquery, s3fs/fsspec, NumPy, Docker, GitHub Actions, Google Cloud Run, Google Cloud Storage, Amazon S3 (AWS Open Data).

---

## NASA Data

- **SPHEREx Spectral Images (Level 2)**, Data Release 1 and Quick Release 3 – NASA/IPAC Infrared Science Archive (IRSA). Accessed through IRSA's SIA/TAP services and the IRSA cutout service, and from the official SPHEREx copy on Amazon S3 (`s3://nasa-irsa-spherex`, AWS Open Data Sponsorship Program).
  Credit: NASA/IPAC Infrared Science Archive (IRSA), SPHEREx Team.
- **IRSA SPHEREx tutorial notebooks** (Caltech-IPAC, BSD-3-Clause) – used as a reference for data access, cutouts and the spectral WCS.

## Space Agency Partner Data and Other References

- **ESA Gaia Data Release 3** – positions and proper motions used to validate that stars appear where they should (science module), and all Gaia stars in each field shown as an overlay (catalogue I/355/gaiadr3 through the VizieR service, CDS Strasbourg, and its mirrors).
- **SIMBAD** (CDS, Strasbourg) – target name resolution.
- Software: Astropy, Astroquery, reproject, NumPy, SciPy, Matplotlib, Pillow, FastAPI, Uvicorn, s3fs/fsspec (all open source).
- Hosting: Google Cloud Run and Cloud Storage (Space Apps Global Offer credit).

---

## Use of Super Intelligence (SI) – backend part

Yes. We used Claude (Anthropic), an AI assistant, during the backend work: it helped explain the challenge and the SPHEREx data, suggested how to split the work and structure the API, wrote and reviewed much of the FastAPI server, the S3 partial-read downloader and the caching logic, found IRSA documentation (cloud access, SIA/TAP), and walked us through deploying on Google Cloud Run. We ran and verified the results ourselves, including speed tests, checking that the S3 data is identical to IRSA's, and checking that Barnard's Star moves in the expected direction. AI-assisted source files are marked with an "AI-assisted" note in their file headers.
