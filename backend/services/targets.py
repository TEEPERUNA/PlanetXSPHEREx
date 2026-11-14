"""
Predefined benchmark targets for the NASA Space Apps Challenge (Planet X & SPHEREx).
Contains ground-truth astronomical coordinates, proper motions, and scientific metadata.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class TargetInfo:
    id: str
    name: str
    target_type: str
    ra_deg: float
    dec_deg: float
    ra_hms: str
    dec_dms: str
    proper_motion_ra_mas: float  # pmra * cos(dec) in mas/yr
    proper_motion_dec_mas: float # pmdec in mas/yr
    parallax_mas: float
    primary_bands: List[str]     # Optimal SPHEREx/WISE detector bands (e.g. D1-D6)
    science_phenomenon: str
    instructions_for_detection: str
    gaia_dr3_source_id: Optional[int] = None
    period_days: Optional[float] = None

BENCHMARK_TARGETS: Dict[str, TargetInfo] = {
    "barnard": TargetInfo(
        id="barnard",
        name="Barnard's Star",
        target_type="High Proper Motion Red Dwarf (M4V)",
        ra_deg=269.452075,
        dec_deg=4.693392,
        ra_hms="17h 57m 48.50s",
        dec_dms="+04° 41′ 36.2″",
        proper_motion_ra_mas=-798.58,
        proper_motion_dec_mas=10328.2,
        parallax_mas=547.45,
        primary_bands=["D1", "D2", "D3", "ALL"],
        science_phenomenon="Largest known proper motion in the sky (~10.39 arcsec/yr).",
        instructions_for_detection=(
            "Blink between two epochs to see the prominent jump in position. "
            "In difference imaging (Epoch2 - Epoch1), observe the classic dipole: "
            "a dark subtraction pit at the old position and a bright peak at the new position."
        ),
        gaia_dr3_source_id=4472832130942585856
    ),
    "wise0855": TargetInfo(
        id="wise0855",
        name="WISE 0855-0714",
        target_type="Cold Sub-Brown Dwarf (Y-dwarf)",
        ra_deg=133.786245,
        dec_deg=-7.244372,
        ra_hms="08h 55m 10.83s",
        dec_dms="-07° 14′ 42.5″",
        proper_motion_ra_mas=-8132.0,
        proper_motion_dec_mas=687.0,
        parallax_mas=433.0,
        primary_bands=["D5", "D6", "Band 2 (4.6 µm)"],
        science_phenomenon="Coldest known planetary-mass brown dwarf (T ~ 250 K), ~8.16 arcsec/yr motion.",
        instructions_for_detection=(
            "Invisible in short optical/NIR bands (D1-D3). Switch detector band to D5/D6 (or unWISE W2 4.6 µm). "
            "Apply ZScale stretch with negative inversion (invert=1) and ZODI background subtraction. "
            "The moving brown dwarf will appear as a faint dot moving against static background galaxies."
        ),
        gaia_dr3_source_id=None # Too cold/faint in optical for Gaia
    ),
    "eps_indi_b": TargetInfo(
        id="eps_indi_b",
        name="Epsilon Indi B",
        target_type="Brown Dwarf Binary System (T1 + T6)",
        ra_deg=331.04375,
        dec_deg=-56.782778,
        ra_hms="22h 04m 10.50s",
        dec_dms="-56° 46′ 58.0″",
        proper_motion_ra_mas=3961.4,
        proper_motion_dec_mas=-2538.3,
        parallax_mas=275.8,
        primary_bands=["D2", "D3", "D4"],
        science_phenomenon="Binary brown dwarf companion moving with bright host star eps Indi A.",
        instructions_for_detection=(
            "The bright primary star eps Indi A produces a bright diffraction halo. "
            "Difference imaging cancels the static core of the halo, revealing the brown dwarf "
            "companion moving in lockstep with the common proper motion."
        ),
        gaia_dr3_source_id=6412595995574316544
    ),
    "rw_aur": TargetInfo(
        id="rw_aur",
        name="RW Aurigae",
        target_type="Classical T Tauri Variable Star",
        ra_deg=76.956417,
        dec_deg=30.401417,
        ra_hms="05h 07m 49.54s",
        dec_dms="+30° 24′ 05.1″",
        proper_motion_ra_mas=0.74,
        proper_motion_dec_mas=-18.41,
        parallax_mas=6.13,
        primary_bands=["D1", "D2", "D3", "D4"],
        science_phenomenon="Cataclysmic / eruptive photometric dips due to circumstellar dust occultation.",
        instructions_for_detection=(
            "Check the multi-epoch light curve. Observe major flux variations (up to 3 magnitudes drop). "
            "Examine SPHEREx 102-channel NIR spectrum to observe thermal emission from the circumstellar dust disk."
        ),
        gaia_dr3_source_id=162608123281132544
    ),
    "r_dra": TargetInfo(
        id="r_dra",
        name="R Draconis",
        target_type="Mira-type Pulsating Red Giant",
        ra_deg=248.167625,
        dec_deg=66.755056,
        ra_hms="16h 32m 40.23s",
        dec_dms="+66° 45′ 18.2″",
        proper_motion_ra_mas=9.12,
        proper_motion_dec_mas=12.44,
        parallax_mas=1.38,
        primary_bands=["D1", "D2", "D3", "D4", "D5", "D6"],
        science_phenomenon="Long-period Mira pulsation (~245.6 days), massive visual flux amplitude (mag 6.7 to 13.2).",
        instructions_for_detection=(
            "Blink between epochs separated by ~4 months (half-cycle) to observe drastic brightening and dimming. "
            "Difference image will display a giant bright or dark centroid without dipole displacement. "
            "Spectrum reveals characteristic deep molecular absorption bands (water vapor, CO, titanium oxide)."
        ),
        gaia_dr3_source_id=1646271926618580736,
        period_days=245.6
    )
}

def get_target(identifier: str) -> Optional[TargetInfo]:
    key = identifier.lower().replace(" ", "").replace("'", "").replace("-", "_")
    for k, target in BENCHMARK_TARGETS.items():
        if k in key or key in k:
            return target
    return None
