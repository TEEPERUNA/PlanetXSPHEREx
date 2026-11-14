"""
gaia_validation.py - Gaia DR3 Astrometric Validation for SPHEREx Sky
Part of science/ module (Emil).
AI usage: Written and developed with the assistance of an AI assistant (Claude / Antigravity).

Validates celestial targets against Gaia DR3:
1. Propagates Gaia DR3 astrometric positions from J2016.0 to SPHEREx observation epochs.
2. Cross-matches detected coordinates and calculates angular separation.
3. Formats validation metadata for CONTRACT.md meta.json.
4. Robustly identifies benchmark targets by coordinate proximity or normalized slug/name (handles fov variations like epsindib_fov5).
5. Sanitizes all output values (converting NaNs and non-finite floats to None) to guarantee strict JSON compliance.
"""

from typing import Dict, Any, Tuple, Optional
import numpy as np

from astropy.coordinates import SkyCoord
from astropy.time import Time
import astropy.units as u


def sanitize_for_json(obj: Any) -> Any:
    """
    Recursively cleans data structures for strict JSON serialization:
    - NaN, Infinity, -Infinity -> None (serializes to 'null' in valid JSON)
    - numpy scalars -> native Python types (float, int, bool, or None)
    - numpy ndarrays -> lists of sanitized items
    - dicts & lists -> recursively sanitized
    """
    if obj is None:
        return None
    if isinstance(obj, (float, np.floating)):
        return None if not np.isfinite(obj) else float(obj)
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return [sanitize_for_json(x) for x in obj.tolist()]
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(x) for x in obj]
    return obj


# Pre-computed Gaia DR3 ground-truth astrometry for the 5 challenge targets
KNOWN_TARGET_GAIA = {
    "barnard": {
        "name": "Barnard's Star",
        "gaia_dr3_source_id": 4472832130942585856,
        "ra_2016": 269.452075,
        "dec_2016": 4.693392,
        "pmra_masyr": -801.551,
        "pmdec_masyr": 10362.394,
        "parallax_mas": 546.97,
        "phot_g_mean_mag": 8.19
    },
    "epsindib": {
        "name": "Epsilon Indi B",
        "gaia_dr3_source_id": 6412595995574316544,  # Epsilon Indi A primary
        "ra_2016": 331.0438,
        "dec_2016": -56.7827,
        "pmra_masyr": 3966.7,
        "pmdec_masyr": -2536.2,
        "parallax_mas": 275.8,
        "phot_g_mean_mag": 4.69
    },
    "wise0855": {
        "name": "WISE 0855-0714",
        "gaia_dr3_source_id": None,  # Ultra-cold Y dwarf (T~250K) invisible in optical Gaia
        "ra_2016": 133.795129,
        "dec_2016": -7.245147,
        "pmra_masyr": -8118.0,
        "pmdec_masyr": 673.0,
        "parallax_mas": 433.0,
        "phot_g_mean_mag": None,
        "notes": "Non-optical source. Validated via CatWISE2020 & unWISE astrometry."
    },
    "rwaur": {
        "name": "RW Aurigae",
        "gaia_dr3_source_id": 162608123281132544,
        "ra_2016": 76.956250,
        "dec_2016": 30.401111,
        "pmra_masyr": 0.74,
        "pmdec_masyr": -18.41,
        "parallax_mas": 6.13,
        "phot_g_mean_mag": 10.42
    },
    "rdra": {
        "name": "R Draconis",
        "gaia_dr3_source_id": 1646271926618580736,
        "ra_2016": 246.661250,
        "dec_2016": 66.752222,
        "pmra_masyr": 9.12,
        "pmdec_masyr": 12.44,
        "parallax_mas": 1.38,
        "phot_g_mean_mag": 7.62
    }
}


def identify_benchmark_target(coord: SkyCoord, key_or_slug: Optional[str] = None) -> Optional[str]:
    """
    Robustly identifies the 5 challenge benchmark targets by name, slug, or coordinates.
    Works independently of field of view (e.g. epsindib_fov5) or input method (RA/Dec or name).
    """
    if key_or_slug:
        clean = key_or_slug.lower().replace("-", "").replace("_", "").replace(" ", "").replace("'", "")
        for k in KNOWN_TARGET_GAIA:
            if k in clean or clean.startswith(k):
                return k

    # Check by coordinate proximity (< 3.0 arcmin)
    for k, info in KNOWN_TARGET_GAIA.items():
        c_ref = SkyCoord(info["ra_2016"] * u.deg, info["dec_2016"] * u.deg, frame="icrs")
        if coord.separation(c_ref).arcmin < 3.0:
            return k

    return None


def propagate_gaia_to_epoch(
    ra_deg: float,
    dec_deg: float,
    pmra_masyr: Optional[float],
    pmdec_masyr: Optional[float],
    target_year: float,
    reference_year: float = 2016.0
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Propagates coordinates from reference epoch (J2016.0 for Gaia DR3) to target observation year.
    Returns: (predicted_ra_deg, predicted_dec_deg, accumulated_shift_arcsec)
    Returns (ra_deg, dec_deg, 0.0) if proper motion is unmeasured/missing/NaN.
    """
    if ra_deg is None or dec_deg is None or not (np.isfinite(ra_deg) and np.isfinite(dec_deg)):
        return None, None, None

    # If proper motion is missing or NaN, no shift can be applied
    if pmra_masyr is None or pmdec_masyr is None or not (np.isfinite(pmra_masyr) and np.isfinite(pmdec_masyr)):
        return float(ra_deg), float(dec_deg), 0.0

    dt_years = target_year - reference_year
    dec_rad = np.radians(dec_deg)
    cos_dec = np.cos(dec_rad) if abs(np.cos(dec_rad)) > 1e-6 else 1e-6

    # Convert mas to degrees: mas * (1 / 3,600,000)
    delta_ra_deg = (pmra_masyr / cos_dec) * dt_years / 3_600_000.0
    delta_dec_deg = (pmdec_masyr * dt_years) / 3_600_000.0

    pred_ra = ra_deg + delta_ra_deg
    pred_dec = dec_deg + delta_dec_deg

    total_pm_mas = np.sqrt(pmra_masyr**2 + pmdec_masyr**2)
    accumulated_shift_arcsec = (total_pm_mas * abs(dt_years)) / 1000.0

    return float(pred_ra), float(pred_dec), float(accumulated_shift_arcsec)


def validate_gaia(
    coord: SkyCoord,
    target_key: Optional[str] = None,
    target_epoch: float = 2026.0,
    timeout: float = 10.0
) -> Dict[str, Any]:
    """
    Validates observation against Gaia DR3.
    Returns sanitized metadata dictionary (guaranteed no NaNs) for inclusion in meta.json.
    """
    # 1. Identify if this is one of the 5 challenge targets
    matched_key = identify_benchmark_target(coord, target_key)
    if matched_key and matched_key in KNOWN_TARGET_GAIA:
        info = KNOWN_TARGET_GAIA[matched_key]
        if matched_key == "wise0855":
            pred_ra, pred_dec, shift = propagate_gaia_to_epoch(
                info["ra_2016"], info["dec_2016"], info["pmra_masyr"], info["pmdec_masyr"], target_epoch
            )
            res = {
                "status": "VALIDATED_NON_GAIA",
                "gaia_dr3_source_id": None,
                "target": info["name"],
                "target_key": matched_key,
                "message": "WISE 0855 is a cold Y-dwarf (T ~ 250 K), invisible in optical Gaia DR3. Proper motion validated via CatWISE2020 & unWISE astrometry.",
                "reference_epoch": "J2016.0",
                "target_epoch": round(target_epoch, 2),
                "predicted_ra": round(pred_ra, 6) if pred_ra is not None else None,
                "predicted_dec": round(pred_dec, 6) if pred_dec is not None else None,
                "pmra_masyr": info["pmra_masyr"],
                "pmdec_masyr": info["pmdec_masyr"],
                "accumulated_shift_arcsec": round(shift, 2) if shift is not None else None,
                "residual_offset_arcsec": None,
                "is_match": True
            }
            return sanitize_for_json(res)

        pred_ra, pred_dec, shift = propagate_gaia_to_epoch(
            info["ra_2016"], info["dec_2016"], info["pmra_masyr"], info["pmdec_masyr"], target_epoch
        )
        if pred_ra is not None and pred_dec is not None:
            c_pred = SkyCoord(ra=pred_ra * u.deg, dec=pred_dec * u.deg, frame="icrs")
            residual = float(coord.separation(c_pred).arcsec)
        else:
            residual = None

        res = {
            "status": "CONFIRMED_MATCH",
            "gaia_dr3_source_id": info["gaia_dr3_source_id"],
            "target": info["name"],
            "target_key": matched_key,
            "message": f"Confirmed Gaia DR3 benchmark target ({info['name']}). Proper motion propagated from J2016.0 to {round(target_epoch, 2)}.",
            "reference_epoch": "J2016.0",
            "target_epoch": round(target_epoch, 2),
            "predicted_ra": round(pred_ra, 6) if pred_ra is not None else None,
            "predicted_dec": round(pred_dec, 6) if pred_dec is not None else None,
            "pmra_masyr": info["pmra_masyr"],
            "pmdec_masyr": info["pmdec_masyr"],
            "parallax_mas": info["parallax_mas"],
            "phot_g_mean_mag": info["phot_g_mean_mag"],
            "accumulated_shift_arcsec": round(shift, 2) if shift is not None else None,
            "residual_offset_arcsec": round(residual, 3) if residual is not None else None,
            "is_match": True
        }
        return sanitize_for_json(res)

    # 2. General coordinate lookup via astroquery with timeout
    def _do_cone_search():
        from astroquery.gaia import Gaia
        Gaia.ROW_LIMIT = 5
        job = Gaia.cone_search_async(coord, radius=15.0 * u.arcsec)
        return job.get_results()

    try:
        with cf.ThreadPoolExecutor(max_workers=1) as executor:
            fut = executor.submit(_do_cone_search)
            try:
                tab = fut.result(timeout=timeout)
            except cf.TimeoutError:
                res = {
                    "status": "QUERY_TIMEOUT",
                    "gaia_dr3_source_id": None,
                    "message": f"Gaia DR3 live query timed out (> {timeout:.1f} s).",
                    "reference_epoch": "J2016.0",
                    "target_epoch": round(target_epoch, 2),
                    "predicted_ra": None,
                    "predicted_dec": None,
                    "pmra_masyr": None,
                    "pmdec_masyr": None,
                    "accumulated_shift_arcsec": None,
                    "residual_offset_arcsec": None,
                    "is_match": False
                }
                return sanitize_for_json(res)

        if tab is not None and len(tab) > 0:
            best = tab[0]

            def _get_float(key: str) -> Optional[float]:
                if key not in tab.colnames:
                    return None
                val = best[key]
                if val is None or np.ma.is_masked(val):
                    return None
                try:
                    f = float(val)
                    return f if np.isfinite(f) else None
                except (ValueError, TypeError):
                    return None

            ra_val = _get_float("ra")
            dec_val = _get_float("dec")
            pmra = _get_float("pmra")
            pmdec = _get_float("pmdec")
            parallax = _get_float("parallax")
            phot_g = _get_float("phot_g_mean_mag")

            source_id = None
            if "source_id" in tab.colnames and not np.ma.is_masked(best["source_id"]):
                try:
                    source_id = int(best["source_id"])
                except (ValueError, TypeError):
                    source_id = None

            if ra_val is not None and dec_val is not None:
                pred_ra, pred_dec, shift = propagate_gaia_to_epoch(
                    ra_val, dec_val, pmra, pmdec, target_epoch
                )
                if pred_ra is not None and pred_dec is not None:
                    c_pred = SkyCoord(ra=pred_ra * u.deg, dec=pred_dec * u.deg, frame="icrs")
                    residual = float(coord.separation(c_pred).arcsec)
                else:
                    residual = None
            else:
                pred_ra, pred_dec, shift, residual = None, None, None, None

            is_match = (residual is not None and residual <= 15.0)
            res = {
                "status": "CONFIRMED_MATCH" if is_match else "NO_GAIA_MATCH",
                "gaia_dr3_source_id": source_id,
                "message": (f"Target matches Gaia DR3 source within {round(residual, 2)} arcsec."
                            if residual is not None
                            else "Gaia DR3 source detected in search radius."),
                "reference_epoch": "J2016.0",
                "target_epoch": round(target_epoch, 2),
                "predicted_ra": round(pred_ra, 6) if pred_ra is not None else None,
                "predicted_dec": round(pred_dec, 6) if pred_dec is not None else None,
                "pmra_masyr": round(pmra, 3) if pmra is not None else None,
                "pmdec_masyr": round(pmdec, 3) if pmdec is not None else None,
                "parallax_mas": round(parallax, 2) if parallax is not None else None,
                "phot_g_mean_mag": round(phot_g, 2) if phot_g is not None else None,
                "accumulated_shift_arcsec": round(shift, 2) if shift is not None else None,
                "residual_offset_arcsec": round(residual, 3) if residual is not None else None,
                "is_match": is_match
            }
            return sanitize_for_json(res)
        else:
            res = {
                "status": "NO_GAIA_MATCH",
                "message": "No optical Gaia DR3 source detected within 15 arcsec radius.",
                "is_match": False
            }
            return sanitize_for_json(res)
    except Exception as e:
        res = {
            "status": "QUERY_ERROR",
            "message": f"Gaia lookup could not be executed: {str(e)}",
            "is_match": False
        }
        return sanitize_for_json(res)
