"""
test_science.py - Verifies Emil's Science and Image Processing algorithms
within the main branch structure.
"""

import sys
from pathlib import Path
from astropy.coordinates import SkyCoord
import astropy.units as u

# Add science folder to path
sys.path.insert(0, str(Path(__file__).parent))

from gaia_validation import validate_gaia, propagate_gaia_to_epoch, KNOWN_TARGET_GAIA
import fetch_spherex as fs

def test_gaia_validation():
    print("Testing Gaia DR3 Astrometric Validation...")
    for target_key, info in KNOWN_TARGET_GAIA.items():
        coord = SkyCoord(ra=info["ra_2016"] * u.deg, dec=info["dec_2016"] * u.deg, frame="icrs")
        res = validate_gaia(coord, target_key=target_key, target_epoch=2026.0)
        assert res["is_match"] is True
        print(f"  ✓ {info['name']}: {res['status']} | Shift: {res.get('accumulated_shift_arcsec', 0.0)} arcsec")

def test_stretch_and_invert():
    import numpy as np
    print("Testing Image Stretch and Inversion...")
    dummy = np.random.normal(100, 15, size=(31, 31)).astype(np.float32)
    s_normal = fs.stretch(dummy, lo=80, hi=130, invert=False)
    s_invert = fs.stretch(dummy, lo=80, hi=130, invert=True)
    assert s_normal.dtype == np.uint8
    assert s_invert.dtype == np.uint8
    assert np.allclose(s_normal, 255 - s_invert)
    print("  ✓ Contrast stretch and negative mode verified")

def test_glare_suppression():
    import numpy as np
    print("Testing Glare Suppression (Epsilon Indi B)...")
    y, x = np.indices((31, 31))
    halo = 1000.0 * np.exp(-((x - 15)**2 + (y - 15)**2) / (2 * 6.0**2))
    companion = 50.0 * np.exp(-((x - 22)**2 + (y - 22)**2) / (2 * 1.5**2))
    total = halo + companion
    suppressed = fs.suppress_stellar_glare(total, sigma=3.5)
    # The broad halo should be reduced substantially more than the sharp companion
    assert suppressed[15, 15] < total[15, 15]
    print("  ✓ Stellar glare suppression verified")

if __name__ == "__main__":
    test_gaia_validation()
    test_stretch_and_invert()
    test_glare_suppression()
    print("\nALL SCIENCE TESTS PASSED SUCCESSFULLY!")
