"""Independent numeric checks, outside the timed codec calls."""
from __future__ import annotations

import math
import numpy as np


def evaluate(original: np.ndarray, reconstructed: np.ndarray, bound: float) -> dict:
    if not isinstance(reconstructed, np.ndarray):
        raise TypeError("decompress() must return a numpy.ndarray")
    if reconstructed.shape != original.shape:
        raise ValueError(f"reconstructed shape {reconstructed.shape} != original {original.shape}")
    if reconstructed.dtype != original.dtype:
        raise ValueError(f"reconstructed dtype {reconstructed.dtype} != original {original.dtype}")
    if not np.isfinite(reconstructed).all():
        raise ValueError("reconstructed array contains NaN or infinity")
    with np.errstate(over="ignore", invalid="ignore"):
        delta = reconstructed.astype(np.float64) - original.astype(np.float64)
    if not np.isfinite(delta).all():
        raise ValueError("error calculation overflowed float64")
    absolute = np.abs(delta)
    max_error = float(np.max(absolute))
    # Scale before squaring so a finite error does not overflow the square.
    rmse = max_error * float(np.sqrt(np.mean((delta / max_error) ** 2))) if max_error else 0.0
    lo, hi = float(np.min(original)), float(np.max(original))
    value_range = hi - lo
    psnr = 20 * (math.log10(value_range) - math.log10(rmse)) if value_range > 0 and rmse > 0 else None
    return {"max_abs_error": max_error, "mean_error": float(np.mean(delta)), "rmse": rmse,
            "psnr_db": psnr, "error_bound_violations": int(np.count_nonzero(absolute > bound)),
            "bound_satisfied": bool(max_error <= bound)}
