"""
FastAPI Server for PlanetXSPHEREx.
Provides REST API endpoints for:
- 5 Challenge Benchmark Targets metadata
- Multi-epoch image processing, contrast stretching, and difference imaging
- 102-channel spectrophotometry and light curves
- Gaia DR3 astrometric validation
"""

from typing import Optional
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.services.targets import BENCHMARK_TARGETS, get_target
from backend.services.pipeline import process_science_pipeline

app = FastAPI(
    title="PlanetXSPHEREx API",
    description="Scientific image processing and multi-epoch visualization for NASA Space Apps Challenge",
    version="1.0.0"
)

# Enable CORS for frontend developers (Eliz & Juho)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {
        "message": "PlanetXSPHEREx Science & Image Processing API is running",
        "docs_url": "/docs",
        "benchmark_targets": list(BENCHMARK_TARGETS.keys())
    }

@app.get("/api/targets")
def list_benchmark_targets():
    """Returns list of the 5 NASA Space Apps challenge benchmark targets."""
    return [
        {
            "id": t.id,
            "name": t.name,
            "type": t.target_type,
            "ra_deg": t.ra_deg,
            "dec_deg": t.dec_deg,
            "ra_hms": t.ra_hms,
            "dec_dms": t.dec_dms,
            "primary_bands": t.primary_bands,
            "science_phenomenon": t.science_phenomenon,
            "instructions": t.instructions_for_detection
        }
        for t in BENCHMARK_TARGETS.values()
    ]

@app.get("/api/targets/{target_id}")
def get_benchmark_target(target_id: str):
    """Returns detailed metadata for a single benchmark target."""
    target = get_target(target_id)
    if not target:
        raise HTTPException(status_code=404, detail=f"Target '{target_id}' not found.")
    return target

@app.get("/api/process")
def process_target(
    target: Optional[str] = Query(None, description="Benchmark target id: barnard, wise0855, eps_indi_b, rw_aur, r_dra"),
    ra: Optional[float] = Query(None, description="Right Ascension in degrees"),
    dec: Optional[float] = Query(None, description="Declination in degrees"),
    stretch: str = Query("zscale", description="Stretch type: zscale, asinh, log, linear, percentile"),
    invert: bool = Query(False, description="Invert colormap / negative image"),
    band: str = Query("ALL", description="Detector band: D1, D2, D3, D4, D5, D6, or ALL")
):
    """
    Main processing endpoint:
    - Generates or aligns multi-epoch frames
    - Calculates difference image (Frame B - Frame A)
    - Generates S/N stacked image
    - Extracts 102-channel near-infrared spectrum
    - Generates multi-epoch light curve
    - Validates against Gaia DR3
    """
    try:
        result = process_science_pipeline(
            target_identifier=target,
            ra_deg=ra,
            dec_deg=dec,
            stretch_type=stretch,
            invert=invert,
            detector_band=band
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image processing error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
