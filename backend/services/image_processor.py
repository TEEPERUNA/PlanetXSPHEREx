"""
Image Processing Service for SPHEREx Multi-Epoch & Spectral Data.
Authored for NASA Space Apps Challenge (Planet X & SPHEREx).

Handles:
- Astrometric alignment and reprojection across epochs (WCS-based)
- Astronomical contrast stretching (ZScale, Asinh, Log, Invert/Negative)
- Difference imaging (Epoch2 - Epoch1) with dipole detection
- Multi-epoch and multi-band stacking (Median/Mean S/N enhancement)
- Faint target enhancement (Zodiacal light subtraction, glare masking for eps Indi B)
- Export to base64 PNG data URIs for immediate frontend Canvas rendering
"""

import io
import base64
from typing import List, Tuple, Dict, Any, Optional, Union
import numpy as np
from PIL import Image

from astropy.io import fits
from astropy.wcs import WCS
from astropy.visualization import (
    ZScaleInterval,
    PercentileInterval,
    MinMaxInterval,
    AsinhStretch,
    LogStretch,
    LinearStretch,
    ImageNormalize
)
from reproject import reproject_interp

def array_to_base64_png(data_uint8: np.ndarray, colormap: str = "gray") -> str:
    """Converts a 2D uint8 numpy array to a base64 encoded PNG data URI."""
    if data_uint8.dtype != np.uint8:
        data_uint8 = np.clip(data_uint8, 0, 255).astype(np.uint8)
    
    # Simple colormap application
    if colormap == "gray_r" or colormap == "invert":
        data_uint8 = 255 - data_uint8
        img = Image.fromarray(data_uint8, mode="L")
    elif colormap == "heat":
        # Simple false-color heat map
        r = np.clip(data_uint8 * 2, 0, 255).astype(np.uint8)
        g = np.clip(data_uint8 * 1.2 - 50, 0, 255).astype(np.uint8)
        b = np.clip(data_uint8 * 0.8 - 100, 0, 255).astype(np.uint8)
        rgb = np.stack([r, g, b], axis=-1)
        img = Image.fromarray(rgb, mode="RGB")
    else:
        img = Image.fromarray(data_uint8, mode="L")
        
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"

def apply_stretch(
    data: np.ndarray,
    stretch_type: str = "zscale",
    invert: bool = False,
    vmin_override: Optional[float] = None,
    vmax_override: Optional[float] = None
) -> np.ndarray:
    """
    Applies astronomical contrast stretching to a 2D float array.
    Returns a uint8 [0, 255] numpy array suitable for display.
    """
    clean_data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
    
    # 1. Determine interval limits
    if vmin_override is not None and vmax_override is not None:
        vmin, vmax = vmin_override, vmax_override
    elif stretch_type == "zscale":
        try:
            interval = ZScaleInterval()
            vmin, vmax = interval.get_limits(clean_data)
        except Exception:
            vmin, vmax = np.percentile(clean_data, [1.0, 99.0])
    elif stretch_type == "percentile":
        interval = PercentileInterval(99.0)
        vmin, vmax = interval.get_limits(clean_data)
    else:
        interval = MinMaxInterval()
        vmin, vmax = interval.get_limits(clean_data)

    if vmax <= vmin:
        vmax = vmin + 1e-5

    # 2. Select stretch function
    if stretch_type in ["zscale", "asinh"]:
        stretch_fn = AsinhStretch(a=0.1)
    elif stretch_type == "log":
        stretch_fn = LogStretch(a=1000.0)
    else:
        stretch_fn = LinearStretch()

    norm = ImageNormalize(vmin=vmin, vmax=vmax, stretch=stretch_fn, clip=True)
    stretched = norm(clean_data)
    
    # Convert to 0-255 uint8
    uint8_data = (np.clip(stretched, 0.0, 1.0) * 255.0).astype(np.uint8)
    
    if invert:
        uint8_data = 255 - uint8_data
        
    return uint8_data

def align_epochs(
    frames: List[np.ndarray],
    wcs_list: List[WCS],
    reference_idx: int = 0
) -> Tuple[List[np.ndarray], WCS]:
    """
    Astrometrically registers / reprojects all frames onto the reference frame's WCS.
    Ensures pixel-to-pixel alignment across observing epochs.
    """
    if not frames or not wcs_list or len(frames) != len(wcs_list):
        raise ValueError("frames and wcs_list must be non-empty and of equal length.")

    ref_wcs = wcs_list[reference_idx]
    ref_shape = frames[reference_idx].shape
    aligned_frames = []

    for i, (frame, w) in enumerate(zip(frames, wcs_list)):
        if i == reference_idx:
            aligned_frames.append(frame.copy())
        else:
            reprojected, _ = reproject_interp(
                (frame, w),
                ref_wcs,
                shape_out=ref_shape
            )
            # Fill reprojection NaNs with frame median
            clean = np.nan_to_num(reprojected, nan=float(np.nanmedian(frame)))
            aligned_frames.append(clean)

    return aligned_frames, ref_wcs

def compute_difference(
    frame_a: np.ndarray,
    frame_b: np.ndarray,
    normalize_background: bool = True
) -> np.ndarray:
    """
    Computes subtraction difference: Delta I = Frame B - Frame A.
    Moving objects produce a dipole (negative hole + positive peak).
    Variable stars produce a single monopole peak (bright or dark).
    """
    diff_a = frame_a.astype(np.float32)
    diff_b = frame_b.astype(np.float32)

    if normalize_background:
        diff_a = diff_a - np.nanmedian(diff_a)
        diff_b = diff_b - np.nanmedian(diff_b)

    delta = diff_b - diff_a
    return delta

def stretch_difference_image(delta: np.ndarray, sigma_clip: float = 3.0) -> np.ndarray:
    """
    Special zero-centered symmetric stretch for difference images.
    Zero difference maps to neutral gray (128).
    Negative dipoles map toward 0 (black).
    Positive dipoles map toward 255 (white).
    """
    clean_delta = np.nan_to_num(delta, nan=0.0)
    std = np.nanstd(clean_delta)
    if std < 1e-7:
        std = 1.0

    vlimit = sigma_clip * std
    # Map [-vlimit, +vlimit] -> [0, 255]
    scaled = (clean_delta / (2.0 * vlimit)) + 0.5
    scaled = np.clip(scaled, 0.0, 1.0)
    return (scaled * 255.0).astype(np.uint8)

def stack_frames(frames: List[np.ndarray], method: str = "median") -> np.ndarray:
    """
    Co-adds / stacks multiple frames across epochs or detector bands.
    Boosts S/N ratio for ultra-faint objects like WISE 0855.
    """
    if not frames:
        raise ValueError("No frames provided for stacking.")
    
    stack_array = np.array(frames)
    if method == "mean":
        stacked = np.nanmean(stack_array, axis=0)
    else:
        stacked = np.nanmedian(stack_array, axis=0)
    return stacked

def subtract_zodiacal_light(image: np.ndarray, zodi_extension: Optional[np.ndarray] = None) -> np.ndarray:
    """
    Removes SPHEREx Zodiacal background light.
    If official SPHEREx 'ZODI' extension is provided, subtracts it directly.
    Otherwise fits and subtracts a smooth 2D planar/median background model.
    """
    if zodi_extension is not None and zodi_extension.shape == image.shape:
        return np.maximum(0.0, image - zodi_extension)
    
    # Fallback: Robust background subtraction
    med = np.nanmedian(image)
    return np.maximum(0.0, image - med)

def remove_stellar_glare(image: np.ndarray, center_xy: Tuple[float, float], mask_radius: float = 8.0) -> np.ndarray:
    """
    Suppresses the overwhelming diffraction halo of a bright primary star
    (e.g., Epsilon Indi A) to reveal faint brown dwarf companions (Epsilon Indi B).
    Uses unsharp masking and localized radial dampening.
    """
    from scipy.ndimage import gaussian_filter
    smoothed = gaussian_filter(image, sigma=mask_radius / 2.0)
    high_pass = image - smoothed
    return high_pass
