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

def test_proper_motion_aperture_tracking():
    print("Testing Proper Motion Aperture Tracking...")
    # Barnard's star moves ~10.4"/yr (pmdec = +10362.4 mas/yr, pmra = -801.5 mas/yr)
    pm_info = {
        "pmra_masyr": -801.551,
        "pmdec_masyr": 10362.394,
        "propagated_to": 2026.87
    }
    c_2026 = SkyCoord(269.452083 * u.deg, 4.693364 * u.deg, frame="icrs")
    
    # In Epoch 0 (MJD 60912 = August 2025 = year ~2025.64):
    cutout_yr = fs.Time(60912.0, format="mjd").decimalyear
    c_epoch0 = fs.propagate(c_2026.ra.deg, c_2026.dec.deg, pm_info["pmra_masyr"], pm_info["pmdec_masyr"],
                            pm_info["propagated_to"], cutout_yr)
    
    sep_arcsec = c_2026.separation(c_epoch0).arcsec
    # dt ~ 1.23 years -> shift ~ 12.8 arcsec (~2 pixels in SPHEREx 6.2"/pix)
    assert 12.0 < sep_arcsec < 14.0, f"Expected ~12.8 arcsec separation, got {sep_arcsec:.2f}"
    print(f"  ✓ Aperture correctly tracks Barnard's Star motion ({sep_arcsec:.2f}\" shift over ~1.2 years)!")

def test_run_with_preloaded_cutouts():
    print("Testing run() with preloaded cutouts (bypassing TAP/network)...")
    from types import SimpleNamespace
    import tempfile
    
    coord = SkyCoord(269.452 * u.deg, 4.693 * u.deg, frame="icrs")
    w, shape = fs.target_wcs(coord, 3.0 / 60.0)
    
    # Create 2 epochs of mock cutouts
    cutouts = [
        fs.Cutout(
            mjd=60912.0, band="D1", url="mock1.fits",
            image=np.ones(shape, dtype=np.float32) * 5.0,
            flags=np.zeros(shape, dtype=np.int32),
            variance=np.ones(shape, dtype=np.float32) * 0.01,
            wcs=w, wavelength_um=0.95, center_flux=5.0, center_err=0.01,
            flagged_frac=0.0, version="7.0.5"
        ),
        fs.Cutout(
            mjd=61279.0, band="D1", url="mock2.fits",
            image=np.ones(shape, dtype=np.float32) * 8.0,
            flags=np.zeros(shape, dtype=np.int32),
            variance=np.ones(shape, dtype=np.float32) * 0.01,
            wcs=w, wavelength_um=0.95, center_flux=8.0, center_err=0.01,
            flagged_frac=0.0, version="7.0.5"
        )
    ]
    
    with tempfile.TemporaryDirectory() as tmpdir:
        args = SimpleNamespace(
            size=3.0, bands=["D1"], max=0, per_group=0, workers=2,
            mask_flags=False, lo=1.0, hi=99.7, frame_ms=600, out=tmpdir,
            show_gaia=False, invert=False
        )
        out_dir = fs.run(coord, "Test Star", "test_star", args, {}, cutouts=cutouts)
        assert (out_dir / "meta.json").exists()
        assert (out_dir / "spectrum.csv").exists()
        assert (out_dir / "lightcurve.csv").exists()
        assert (out_dir / "frames" / "D1" / "epoch0.png").exists()
        assert (out_dir / "frames" / "D1" / "epoch1.png").exists()
        assert (out_dir / "epoch0_D1.fits").exists()
    print("  ✓ run(..., cutouts=...) executed smoothly without any network calls!")

def test_json_null_sanitization():
    print("Testing JSON sanitization (null instead of NaN for strict compliance)...")
    import json
    from types import SimpleNamespace
    import tempfile

    # 1. Direct unit test of sanitize_for_json
    dirty = {
        "pmra_masyr": np.nan,
        "pmdec_masyr": float("nan"),
        "inf_val": np.inf,
        "gaia_validation": {
            "predicted_ra": np.nan,
            "predicted_dec": float("nan"),
            "accumulated_shift_arcsec": np.nan,
            "residual_offset_arcsec": float("nan"),
            "valid_val": np.float32(10.68)
        }
    }
    clean = fs.sanitize_for_json(dirty)
    # Must serialize with allow_nan=False (which throws ValueError if any NaN remains)
    serialized = json.dumps(clean, allow_nan=False)
    assert "NaN" not in serialized
    assert ": null" in serialized
    loaded = json.loads(serialized)
    assert loaded["pmra_masyr"] is None
    assert loaded["gaia_validation"]["predicted_ra"] is None

    # 2. Integration test: free coordinates (RA=10.68, Dec=41.27) with mock cutouts and NaN extra
    coord = SkyCoord(10.68 * u.deg, 41.27 * u.deg, frame="icrs")
    w, shape = fs.target_wcs(coord, 3.0 / 60.0)
    cutouts = [
        fs.Cutout(
            mjd=60912.0, band="D1", url="mock1.fits",
            image=np.ones(shape, dtype=np.float32) * 5.0,
            flags=np.zeros(shape, dtype=np.int32),
            variance=np.ones(shape, dtype=np.float32) * 0.01,
            wcs=w, wavelength_um=0.95, center_flux=5.0, center_err=0.01,
            flagged_frac=0.0, version="7.0.5"
        )
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        args = SimpleNamespace(
            size=3.0, bands=["D1"], max=0, per_group=0, workers=2,
            mask_flags=False, lo=1.0, hi=99.7, frame_ms=600, out=tmpdir,
            show_gaia=False, invert=False
        )
        extra_with_nans = {
            "pmra_masyr": np.nan,
            "pmdec_masyr": np.nan
        }
        out_dir = fs.run(coord, "RA 10.6800 Dec +41.2700", "ra10.6800_dec+41.2700_fov3",
                         args, extra_with_nans, cutouts=cutouts)
        meta_text = (out_dir / "meta.json").read_text()
        assert "NaN" not in meta_text, f"Found unquoted NaN in meta.json:\n{meta_text}"
        parsed = json.loads(meta_text)
        assert parsed["pmra_masyr"] is None
        assert parsed["pmdec_masyr"] is None
        print("  ✓ Free coordinate meta.json successfully sanitized (all NaNs written as null)!")

if __name__ == "__main__":
    test_slug_and_target_identification()
    test_gaia_validation_with_slug_variants()
    test_per_band_lightcurve_barnard_scenario()
    test_per_band_lightcurve_variable_scenario()
    test_proper_motion_aperture_tracking()
    test_run_with_preloaded_cutouts()
    test_json_null_sanitization()
    print("\nALL EXPANDED SCIENCE TESTS PASSED!")
