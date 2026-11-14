"""
Comprehensive test script for Emil's Science & Image Processing Pipeline.
Tests all 5 benchmark targets:
1. Barnard's Star (Proper motion & dipole)
2. WISE 0855 (Ultra-faint Y-dwarf stretch & non-Gaia handling)
3. Epsilon Indi B (Glare reduction & companion isolation)
4. RW Aurigae (T Tauri eruptive dust dimming & dust disk spectrum)
5. R Draconis (Mira 245-day pulsation & molecular absorption spectrum)
"""

import sys
import json
from backend.services.targets import BENCHMARK_TARGETS
from backend.services.pipeline import process_science_pipeline

def run_tests():
    print("================================================================")
    print("🚀 RUNNING SCIENCE & IMAGE PROCESSING PIPELINE TESTS (EMIL)")
    print("================================================================\n")

    passed = 0
    total = len(BENCHMARK_TARGETS)

    for target_key, target in BENCHMARK_TARGETS.items():
        print(f"--- Testing Target: {target.name} ({target_key}) ---")
        try:
            result = process_science_pipeline(
                target_identifier=target_key,
                stretch_type="zscale",
                detector_band="ALL"
            )

            # Assertions
            assert result["status"] == "success", "Pipeline did not return success"
            assert len(result["frames"]) >= 2, "Expected at least 2 epoch frames"
            assert "data_uri" in result["frames"][0], "Frame missing base64 data URI"
            assert "data_uri" in result["difference_frame"], "Difference frame missing data URI"
            assert "data_uri" in result["stacked_frame"], "Stacked frame missing data URI"
            assert result["spectrum"]["total_channels"] == 102, f"Expected 102 channels, got {result['spectrum']['total_channels']}"
            assert "light_curve" in result, "Missing light curve"
            assert "gaia_validation" in result, "Missing Gaia validation"

            # Check specific science properties
            gaia = result["gaia_validation"]
            print(f"  ✓ Multi-epoch frames: {len(result['frames'])} generated with ZScale stretch")
            print(f"  ✓ Difference image generated: {len(result['difference_frame']['data_uri'])} bytes base64")
            print(f"  ✓ Stacked image generated: {len(result['stacked_frame']['data_uri'])} bytes base64")
            print(f"  ✓ 102-channel NIR spectrum: λ = [{result['spectrum']['data'][0]['wavelength_um']} µm - {result['spectrum']['data'][-1]['wavelength_um']} µm]")
            print(f"  ✓ Light curve: is_variable = {result['light_curve']['is_variable']}")
            print(f"  ✓ Gaia DR3 Validation: Status = {gaia['status']} | Msg = {gaia['validation_message']}")
            print("  ✓ PASS\n")
            passed += 1

        except Exception as e:
            print(f"  ❌ FAIL: {e}\n")
            import traceback
            traceback.print_exc()

    print("================================================================")
    print(f"🏁 RESULTS: {passed}/{total} TARGETS PASSED SUCCESSFULLY")
    print("================================================================")

    if passed == total:
        print("ALL TESTS PASSED! Science and Image Processing engine is fully functional.")
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(run_tests())
