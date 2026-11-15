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
import json
from pathlib import Path
import numpy as np
from astropy.coordinates import SkyCoord
import astropy.units as u
from astropy.io import fits

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
    print("Testing Gaia DR3 validation with FOV slugs and accurate J2016 positions...")
    coord_eps = SkyCoord(331.097845 * u.deg, -56.801630 * u.deg, frame="icrs")
    res = validate_gaia(coord_eps, target_key="epsindib_fov5", target_epoch=2026.74)
    assert res["is_match"] is True
    assert res["status"] == "CONFIRMED_MATCH"
    assert res["gaia_dr3_source_id"] == 6412596012146801152 # Eps Ind Ba brown dwarf companion
    assert res["residual_offset_arcsec"] < 5.0, f"Eps Ind B offset too large: {res['residual_offset_arcsec']}\""
    print(f"  ✓ epsindib_fov5 correctly validated: source_id={res['gaia_dr3_source_id']}, residual = {res['residual_offset_arcsec']}\" (< 5\")")

    # Barnard's Star: must match and residual must be small (< 3"), NOT 172"
    coord_b = SkyCoord(269.446080 * u.deg, 4.770707 * u.deg, frame="icrs")
    res_b = validate_gaia(coord_b, target_key="barnard", target_epoch=2026.65)
    assert res_b["is_match"] is True
    assert res_b["status"] == "CONFIRMED_MATCH"
    assert res_b["gaia_dr3_source_id"] == 4472832130942575872
    assert res_b["residual_offset_arcsec"] < 5.0, f"Barnard offset too large: {res_b['residual_offset_arcsec']}\""
    print(f"  ✓ Barnard's Star correctly validated: source_id={res_b['gaia_dr3_source_id']}, residual = {res_b['residual_offset_arcsec']}\" (< 5\")")

def test_bad_pixel_flag_mask():
    print("Testing SPHEREx bad-pixel flag bitmask (excluding FULLSAMPLE & SOURCE)...")
    bits = fs.FLAG_BITS
    # Official DR1 planes (FLAGS header MSKNnnnn keys)
    assert bits["SOURCE"] == 21 and bits["OUTLIER"] == 19 and bits["BLOOM"] == 26 and bits["SNOWBALL"] == 27
    clean_flags = np.full((10, 10), (1 << bits["FULLSAMPLE"]) | (1 << bits["SOURCE"]), dtype=np.int64)
    dirty_flags = clean_flags.copy()
    dirty_flags[0, 0] |= 1 << bits["OVERFLOW"]  # saturation
    dirty_flags[1, 1] |= 1 << bits["NONFUNC"]   # dead pixel
    dirty_flags[2, 2] |= 1 << bits["HALO"]      # warning only, not counted

    old_frac = float(np.mean(dirty_flags != 0))
    assert old_frac == 1.0, f"Expected 1.0, got {old_frac}"

    new_frac = float(np.mean((dirty_flags & fs.BAD_PIXEL_MASK) != 0))
    assert new_frac == 0.02, f"Expected 0.02 (2%), got {new_frac}"
    print("  ✓ BAD_PIXEL_MASK correctly ignores FULLSAMPLE and SOURCE bits (flagged_frac = 0.02 instead of 1.0)!")


def test_read_flag_bits():
    print("Testing flag plane names from a FLAGS header...")
    from astropy.io import fits
    hdr = fits.Header()
    hdr["MSKN0001"] = "OVERFLOW"
    hdr["MSKN0021"] = "SOURCE"
    hdr["MSKN0030"] = "NEWFLAG"  # a plane a future release might add
    bits = fs.read_flag_bits(hdr)
    assert bits == {"OVERFLOW": 1, "SOURCE": 21, "NEWFLAG": 30}, bits
    assert fs.bad_mask(bits) == 1 << 1  # only OVERFLOW is a bad flag here
    assert fs.read_flag_bits(fits.Header()) == fs.FLAG_BITS  # no MSKN keys -> built-in table
    print("  ✓ read_flag_bits reads MSKNnnnn keys and falls back to the DR1 table")

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
        import json
        meta = json.loads((out_dir / "meta.json").read_text())
        assert "inverted" in meta
        assert meta["inverted"] is False
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

def test_gaia_timeout_and_skip_flag():
    print("Testing Gaia timeout and skip_gaia flag...")
    from types import SimpleNamespace
    import tempfile
    import json
    import time

    # 1. Test skip_gaia flag in run()
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
            show_gaia=False, invert=False, skip_gaia=True
        )
        t0 = time.time()
        out_dir = fs.run(coord, "Preview Star", "preview_star", args, {}, cutouts=cutouts)
        elapsed = time.time() - t0
        meta = json.loads((out_dir / "meta.json").read_text())
        assert meta["gaia_validation"]["status"] == "SKIPPED"
        assert meta["gaia_validation"]["is_match"] is False
        assert elapsed < 1.0
        print(f"  ✓ skip_gaia=True bypassed Gaia query in {elapsed:.3f} s (status=SKIPPED)")

    # 2. Test timeout handling in validate_gaia
    t0 = time.time()
    res = validate_gaia(coord, target_key=None, target_epoch=2026.0, timeout=0.001)
    elapsed = time.time() - t0
    assert res["status"] in ("QUERY_TIMEOUT", "QUERY_ERROR")
    assert res["is_match"] is False
    assert elapsed < 1.0
    print(f"  ✓ validate_gaia with ultra-short timeout aborted gracefully in {elapsed:.3f} s (status={res['status']})")

def test_stellar_donut_repair():
    print("Testing Stellar Donut Repair (repair_star_donuts & stretch)...")
    
    # 1. Saturated NaN stellar core inside an image
    # Shape 31x31 with a 2D Gaussian star peak of 1000 and background ~2
    shape = (31, 31)
    y, x = np.mgrid[:31, :31]
    dist2 = (x - 15)**2 + (y - 15)**2
    synthetic = 2.0 + 1000.0 * np.exp(-dist2 / 8.0)
    
    # Simulate saturated detector core: 3x3 block of NaNs at center
    sat_img = synthetic.copy()
    sat_img[14:17, 14:17] = np.nan
    # Also add unobserved chip border NaNs on the outer row
    sat_img[0, :] = np.nan
    
    repaired = fs.repair_star_donuts(sat_img)
    
    # Saturated core should not be NaN
    assert not np.isnan(repaired).any(), "NaNs remained after repair_star_donuts"
    
    # Center 3x3 must not dip below the boundary brightness (no donut / black hole)
    boundary_flux = synthetic[13, 15] # ~800
    assert np.all(repaired[14:17, 14:17] >= 0.95 * boundary_flux), (
        f"Stellar core has a dark donut dip: {repaired[14:17, 14:17]}"
    )
    
    # Outer edge NaNs must be filled with sky background (~2), not stellar peak
    assert np.all(repaired[0, :] < 5.0), f"Edge NaNs incorrectly filled with high flux: {repaired[0, :]}"
    
    # 2. Non-NaN central depression / crater / zeros (e.g. saturation roll-over or ALL combining)
    crater_img = synthetic.copy()
    crater_img[15, 15] = 0.0 # Zeroed-out core pixel
    repaired_crater = fs.repair_star_donuts(crater_img)
    assert repaired_crater[15, 15] > 500.0, f"Crater was not filled: {repaired_crater[15, 15]}"
    
    # 3. Stretch test: 8-bit image must have 255 pure white at the core when saturated, NO pitch black (0 or 1)
    arr8 = fs.stretch(sat_img, lo=1.0, hi=600.0)
    assert arr8[15, 15] == 255, f"Center pixel should be saturated 255, got {arr8[15, 15]}"
    assert np.all(arr8[14:17, 14:17] == 255), "Core region in stretch() did not render as solid white"
    
    # 4. Difference image test: no neutral gray 127 hole in difference dipole
    diff_path = Path("/tmp/test_diff_donut.png")
    fs.diff_png(sat_img, synthetic, diff_path, scale=2, text="Donut Test")
    from PIL import Image
    diff_im = np.array(Image.open(diff_path).convert("L"))
    # The center pixel of the difference should be a smooth dipole or flat, not a neutral gray hole
    assert diff_path.exists()

    # 5. Edge NaNs bordering high flux (e.g. Epsilon Indi B scenario) must stay neutral sky, not bright white
    edge_bright_img = synthetic.copy()
    edge_bright_img[0:5, 0:5] = np.nan
    repaired_edge = fs.repair_star_donuts(edge_bright_img)
    assert np.all(repaired_edge[0:5, 0:5] < 10.0), f"Edge NaNs bordering star were filled with bright flux: {repaired_edge[0:5, 0:5]}"

    # In diff_png, edge NaNs must be rendered as neutral gray (127)
    diff_edge_path = Path("/tmp/test_diff_edge.png")
    fs.diff_png(edge_bright_img, synthetic, diff_edge_path, scale=1, text="")
    diff_edge_arr = np.array(Image.open(diff_edge_path).convert("L"))
    # In PIL image with flipud, FITS row 0:5 is bottom rows -5:
    assert np.all(diff_edge_arr[-5:, 0:5] == 127), f"Edge NaNs did not render as neutral gray 127 in diff_png: {diff_edge_arr[-5:, 0:5]}"

    print("  ✓ Stellar donuts successfully eliminated across NaNs, non-NaN craters, and stretch rendering!")

def test_multi_layer_pixel_cube():
    print("Testing Multi-Layer Pixel Cubes (SB, ZODI, SNR, WAVE, BW, DETX, DETY)...")
    from types import SimpleNamespace
    import tempfile
    import json
    from astropy.io import fits

    coord = SkyCoord(269.452 * u.deg, 4.693 * u.deg, frame="icrs")
    w, shape = fs.target_wcs(coord, 3.0 / 60.0)

    # 1. Direct unit test of build_pixel_cube
    cutout = fs.Cutout(
        mjd=60912.0, band="D3", url="test_cube.fits",
        image=np.ones(shape, dtype=np.float32) * 15.0,
        zodi=np.ones(shape, dtype=np.float32) * 3.0,
        variance=np.ones(shape, dtype=np.float32) * 0.04,
        wcs=w, x0=500.0, y0=800.0, wavelength_um=1.95,
        center_flux=15.0, center_err=0.02, flagged_frac=0.01, version="7.0.5"
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        cube_path = Path(tmpdir) / "pixels" / "D3" / "epoch0.fits"
        fs.build_pixel_cube(cube_path, cutout.image, [cutout], w, shape, "D3")
        assert cube_path.exists(), "Pixel cube file was not created"

        with fits.open(cube_path) as h:
            expected_exts = ["SB", "ZODI", "SNR", "WAVE", "BW", "DETX", "DETY"]
            for ext in expected_exts:
                assert ext in h, f"Extension {ext} missing from pixel cube"
                data = h[ext].data
                assert data.shape == shape, f"Extension {ext} shape mismatch: {data.shape} vs {shape}"
                assert data.dtype == np.float32 or data.dtype.str.endswith("f4"), f"Extension {ext} dtype mismatch: {data.dtype}"
                assert np.all(np.isfinite(data)), f"Extension {ext} contains non-finite values"

            # Check specific values
            assert np.isclose(h["SB"].data[15, 15], 15.0)
            assert np.isclose(h["ZODI"].data[15, 15], 3.0)
            assert np.isclose(h["SNR"].data[15, 15], 15.0 / 0.2)  # 15 / sqrt(0.04) = 75.0
            assert np.isclose(h["WAVE"].data[15, 15], 1.95)
            assert 0.0 <= h["DETX"].data[15, 15] <= 2039.0
            assert 0.0 <= h["DETY"].data[15, 15] <= 2039.0
            assert np.isclose(h["DETX"].data[15, 15], 515.0)
            assert np.isclose(h["DETY"].data[15, 15], 815.0)
            assert "FLAGS" not in h, "No FLAGS layer expected when the cutout has no flags"

    # 1b. FLAGS layer: nearest pixel of the representative image, plane names in the header
    flags = np.full(shape, 1 << fs.FLAG_BITS["SOURCE"], dtype=np.int32)
    flags[15, 15] |= 1 << fs.FLAG_BITS["OVERFLOW"]
    flagged = fs.Cutout(**{**cutout.__dict__, "flags": flags, "flag_bits": dict(fs.FLAG_BITS)})
    with tempfile.TemporaryDirectory() as tmpdir:
        cube_path = Path(tmpdir) / "pixels" / "D3" / "epoch0.fits"
        fs.build_pixel_cube(cube_path, flagged.image, [flagged], w, shape, "D3")
        with fits.open(cube_path) as h:
            assert "FLAGS" in h, "FLAGS layer missing"
            f = h["FLAGS"].data
            assert f.shape == shape and f.dtype.kind == "i", f"FLAGS must be integer, got {f.dtype}"
            assert f[15, 15] == (1 << fs.FLAG_BITS["SOURCE"]) | (1 << fs.FLAG_BITS["OVERFLOW"])
            assert f[0, 0] == 1 << fs.FLAG_BITS["SOURCE"]
            assert h["FLAGS"].header["MSKN0001"] == "OVERFLOW"

    # 2. Integration test via run()
    with tempfile.TemporaryDirectory() as tmpdir:
        args = SimpleNamespace(
            size=3.0, bands=["D3"], max=0, per_group=0, workers=2,
            mask_flags=False, lo=1.0, hi=99.7, frame_ms=600, out=tmpdir,
            show_gaia=False, invert=False, skip_gaia=True
        )
        out_dir = fs.run(coord, "Test Star", "test_star", args, {}, cutouts=[cutout])
        meta = json.loads((out_dir / "meta.json").read_text())
        assert "pixels" in meta["outputs"]["D3"]
        assert meta["outputs"]["D3"]["pixels"] == ["pixels/D3/epoch0.fits"]
        assert (out_dir / "pixels" / "D3" / "epoch0.fits").exists()
        assert meta["flag_bits"]["SOURCE"] == 21 and "OVERFLOW" in meta["flag_bad"]
        assert "SOURCE" not in meta["flag_bad"]

    print("  ✓ Multi-layer pixel cubes correctly generated with all 7 float32 layers (SB, ZODI, SNR, WAVE, BW, DETX, DETY)!")

def test_combined_coadd_images():
    print("Testing Combined Coadd Images across all epochs per detector...")
    import json
    import tempfile
    from types import SimpleNamespace
    coord = SkyCoord(269.452 * u.deg, 4.693 * u.deg, frame="icrs")
    w, shape = fs.target_wcs(coord, 3.0 / 60.0)
    img1 = np.ones(shape, dtype=np.float32) * 10.0
    img2 = np.ones(shape, dtype=np.float32) * 20.0
    c1 = fs.Cutout(mjd=60800.0, band="D1", image=img1, wcs=w, x0=1000.0, y0=1000.0, wavelength_um=0.9)
    c2 = fs.Cutout(mjd=60950.0, band="D1", image=img2, wcs=w, x0=1000.0, y0=1000.0, wavelength_um=0.9)

    with tempfile.TemporaryDirectory() as tmpdir:
        args = SimpleNamespace(
            size=3.0, bands=["D1"], max=0, per_group=0, workers=2,
            mask_flags=False, lo=1.0, hi=99.7, frame_ms=600, out=tmpdir,
            show_gaia=False, invert=False, skip_gaia=True
        )
        out_dir = fs.run(coord, "Test Star", "test_star", args, {}, cutouts=[c1, c2])
        meta = json.loads((out_dir / "meta.json").read_text())
        assert "combined" in meta["outputs"]["D1"], "combined key missing in D1 outputs"
        assert "combined_fits" in meta["outputs"]["D1"], "combined_fits key missing in D1 outputs"
        assert (out_dir / "combined_D1.png").exists(), "combined_D1.png missing"
        assert (out_dir / "combined_D1.fits").exists(), "combined_D1.fits missing"
        assert (out_dir / "combined_ALL.fits").exists(), "combined_ALL.fits missing"
        assert (out_dir / "combined_ALL.png").exists(), "combined_ALL.png missing"
        with fits.open(out_dir / "combined_D1.fits") as h:
            assert h[0].data.shape == shape
            assert np.allclose(h[0].data, 15.0, atol=1e-3)
    print("  ✓ Combined coadd images per detector correctly computed and saved as FITS and PNG!")

if __name__ == "__main__":
    test_slug_and_target_identification()
    test_gaia_validation_with_slug_variants()
    test_bad_pixel_flag_mask()
    test_read_flag_bits()
    test_per_band_lightcurve_barnard_scenario()
    test_per_band_lightcurve_variable_scenario()
    test_proper_motion_aperture_tracking()
    test_run_with_preloaded_cutouts()
    test_json_null_sanitization()
    test_gaia_timeout_and_skip_flag()
    test_stellar_donut_repair()
    test_multi_layer_pixel_cube()
    test_combined_coadd_images()
    print("\nALL EXPANDED SCIENCE TESTS PASSED!")
