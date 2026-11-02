"""Simple Python API for benchmarking one array and one compressor."""
from __future__ import annotations

import numpy as np
from .api import AbsoluteError
from .registry import Registry
from .runner import run_trial


def benchmark(data, *, compressor: str, error: AbsoluteError, options=None):
    """Run one checked CPU trial; durations are adapter wall-clock times.

    For repetitions, provenance, and on-disk results use the YAML CLI runner.
    """
    if not isinstance(data, np.ndarray):
        raise TypeError("data must be a numpy.ndarray")
    if data.dtype.kind != "f" or data.dtype.itemsize not in (4, 8) or not data.dtype.isnative:
        raise ValueError("data must have native-endian float32 or float64 dtype")
    if data.size == 0 or not np.isfinite(data).all():
        raise ValueError("data must be non-empty and contain only finite values")
    if not isinstance(error, AbsoluteError):
        raise TypeError("error must be an AbsoluteError")
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise TypeError("options must be a dictionary")
    array = np.ascontiguousarray(data)
    info, metrics = run_trial(Registry(), compressor, options, array, error)
    return {"status": "ok" if metrics["bound_satisfied"] else "violation",
            "compressor": compressor, "compressor_version": info,
            "absolute_error_bound": error.value, "shape": list(array.shape),
            "dtype": array.dtype.str, "options": dict(options), "metrics": metrics}
