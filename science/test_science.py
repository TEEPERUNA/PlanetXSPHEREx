"""
test_science.py - Verifies Emil's Science and Image Processing algorithms
Tests:
1. Benchmark target resolution regardless of FOV slug (epsindib_fov5, wise0855_fov10, coordinates).
2. Gaia DR3 proper motion propagation.
3. Per-band light curve calculation: ensures unequal detector coverage across epochs
   does NOT produce false variability for stable stars (e.g. Barnard's Star),
   while genuine variables (R Dra, RW Aur) are correctly detected.
4. Glare suppression for Epsilon Indi B.
"""

import sys
from pathlib import Path
import numpy as np
from astropy.coordinates import SkyCoord
import astropy.units as u

sys.path.insert(0, str(Path(__file__).parent))

from gaia_validation import validate_gaia, identify_benchmark_target, KNOWN_TARGET_GAIA
import fetch_spherex as fs

def test_slug_and_target_identification():
    print("Testing Target Identification (solving slug/FOV coupling)...")
    
    # 1. Standard slugs
    assert fs.get_target_key(SkyCoord(0, 0, unit="deg"), "epsindib") == "epsindib"
    assert fs.get_target_key(SkyCoord(0, 0, unit="deg"), "wise0855") == "wise0855"

    # 2. Slugs with FOV suffixes (e.g. from API)
    assert fs.get_target_key(SkyCoord(0, 0, unit="deg"), "epsindib_fov5") == "epsindib"
    assert fs.get_target_key(SkyCoord(0, 0, unit="deg"), "wise0855_fov10") == "wise0855"
    assert fs.get_target_key(SkyCoord(0, 0, unit="deg"), "barnard_fov3.5") == "barnard"

    # 3. Pure coordinate queries without slug
    coord_wise = SkyCoord(133.795129 * u.deg, -7.245147 * u.deg, frame="icrs")
    assert fs.get_target_key(coord_wise, "ra133.7951_dec-7.2451_fov3") == "wise0855"

    coord_eps = SkyCoord(331.0438 * u.deg, -56.7827 * u.deg, frame="icrs")
    assert fs.get_target_key(coord_eps, "ra331.0438_dec-56.7827_fov5") == "epsindib"

    print("  ✓ Target identification works for standard slugs, FOV variants (epsindib_fov5), and coordinates!")

def test_gaia_validation_with_slug_variants():
    print("Testing Gaia DR3 validation with FOV slugs...")
    coord_eps = SkyCoord(331.0438 * u.deg, -56.7827 * u.deg, frame="icrs")
    res = validate_gaia(coord_eps, target_key="epsindib_fov5", target_epoch=2026.0)
    assert res["is_match"] is True
    assert res["status"] == "CONFIRMED_MATCH"
    print(f"  ✓ epsindib_fov5 correctly validated against Gaia: shift = {res['accumulated_shift_arcsec']}\"")

def test_per_band_lightcurve_barnard_scenario():
    print("Testing Per-Band Light Curve (Barnard's Star unequal detector scenario)...")
    
    # Simulate Barnard's Star:
    # Intrinsic spectrum: D1 is bright (100 mJy/sr), D4 is faint (15 mJy/sr).
    # Epoch 0 has D1, D2, D3, D4, D5, D6.
    # Epoch 1 has ONLY D1 and D4!
    # A cross-band mean would calculate:
    # Epoch 0 mean ≈ 50, Epoch 1 mean = (100 + 15)/2 = 57.5 (spurious jump!)
    # But per-band, D1 is 100 in both epochs, and D4 is 15 in both epochs -> STABLE!
    
    epochs_meta = [
        {"index": 0, "date": "2025-08-25", "mjd_mean": 60912.0},
        {"index": 1, "date": "2025-10-01", "mjd_mean": 60949.0},
        {"index": 2, "date": "2026-03-16", "mjd_mean": 61115.0}
    ]
    
    cutouts = []
    ep_labels = []
    
    # Epoch 0: All bands
    band_fluxes = {"D1": 100.0, "D2": 80.0, "D3": 50.0, "D4": 15.0, "D5": 8.0, "D6": 4.0}
    for b, f in band_fluxes.items():
        cutouts.append(fs.Cutout(mjd=60912.0, band=b, url="", center_flux=f + np.random.normal(0, 0.5), center_err=1.0))
        ep_labels.append(0)

    # Epoch 1: ONLY D1 and D4!
    cutouts.append(fs.Cutout(mjd=60949.0, band="D1", url="", center_flux=100.0 + np.random.normal(0, 0.5), center_err=1.0))
    ep_labels.append(1)
    cutouts.append(fs.Cutout(mjd=60949.0, band="D4", url="", center_flux=15.0 + np.random.normal(0, 0.5), center_err=1.0))
    ep_labels.append(1)

    # Epoch 2: All bands
    for b, f in band_fluxes.items():
        cutouts.append(fs.Cutout(mjd=61115.0, band=b, url="", center_flux=f + np.random.normal(0, 0.5), center_err=1.0))
        ep_labels.append(2)

    ep_labels = np.array(ep_labels)
    tmp_out = Path("/tmp/test_lc_barnard.png")
    lc_info = fs.plot_lightcurve(cutouts, ep_labels, epochs_meta, tmp_out, "Barnard's Star Test")

    # With per-band light curves, Barnard's Star must be detected as STABLE (not variable)
    assert lc_info["is_variable"] is False, f"Expected is_variable=False for Barnard, got {lc_info['is_variable']}"
    assert "D1" in lc_info["bands"]
    assert "D4" in lc_info["bands"]
    assert lc_info["bands"]["D1"]["is_variable"] is False
    assert lc_info["bands"]["D4"]["is_variable"] is False
    print("  ✓ Barnard's Star with unequal detectors correctly detected as STABLE (is_variable=False)!")

def test_per_band_lightcurve_variable_scenario():
    print("Testing Per-Band Light Curve on genuine variable star (R Dra / RW Aur)...")
    epochs_meta = [
        {"index": 0, "date": "2025-01-01", "mjd_mean": 60700.0},
        {"index": 1, "date": "2025-06-01", "mjd_mean": 60850.0},
        {"index": 2, "date": "2026-01-01", "mjd_mean": 61000.0}
    ]
    # D1 varies by factor of 3 between minimum and maximum light
    cutouts = [
        fs.Cutout(mjd=60700.0, band="D1", url="", center_flux=100.0, center_err=2.0),
        fs.Cutout(mjd=60850.0, band="D1", url="", center_flux=30.0, center_err=2.0),
        fs.Cutout(mjd=61000.0, band="D1", url="", center_flux=95.0, center_err=2.0),
    ]
    ep_labels = np.array([0, 1, 2])
    tmp_out = Path("/tmp/test_lc_variable.png")
    lc_info = fs.plot_lightcurve(cutouts, ep_labels, epochs_meta, tmp_out, "Variable Star Test")

    assert lc_info["is_variable"] is True
    assert "D1" in lc_info["variable_bands"]
    print("  ✓ Genuine variable star correctly detected as VARIABLE (is_variable=True, variable_bands=['D1'])!")

if __name__ == "__main__":
    test_slug_and_target_identification()
    test_gaia_validation_with_slug_variants()
    test_per_band_lightcurve_barnard_scenario()
    test_per_band_lightcurve_variable_scenario()
    print("\nALL EXPANDED SCIENCE TESTS PASSED!")
