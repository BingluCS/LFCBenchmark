"""Load named C-order scientific arrays with explicit metadata."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import numpy as np


def load_dataset(spec: dict, config_dir: Path):
    allowed = {"name", "path", "format", "dtype", "shape"}
    unknown = set(spec) - allowed
    if unknown:
        raise ValueError(f"unknown dataset keys: {sorted(unknown)}")
    path = Path(spec["path"]).expanduser()
    if not path.is_absolute():
        path = config_dir / path
    path = path.resolve(strict=True)
    fmt = spec.get("format", "npy" if path.suffix == ".npy" else "raw")
    if fmt == "npy":
        array = np.load(path, allow_pickle=False)
        if not isinstance(array, np.ndarray):
            raise ValueError("npy input must be a single NumPy array")
        if "dtype" in spec and array.dtype != np.dtype(spec["dtype"]):
            raise ValueError("npy dtype does not match the configured dtype")
        if "shape" in spec and array.shape != tuple(spec["shape"]):
            raise ValueError("npy shape does not match the configured shape")
    elif fmt == "raw":
        if "dtype" not in spec or "shape" not in spec:
            raise ValueError("raw input requires dtype and C-order shape")
        dtype = np.dtype(spec["dtype"])
        shape = spec["shape"]
        if not isinstance(shape, list) or not shape or any(not isinstance(x, int) or isinstance(x, bool) or x <= 0 for x in shape):
            raise ValueError("shape must be a non-empty list of positive integers")
        expected = math.prod(shape) * dtype.itemsize
        if path.stat().st_size != expected:
            raise ValueError(f"raw input size mismatch: expected {expected}, got {path.stat().st_size}")
        array = np.fromfile(path, dtype=dtype).reshape(shape, order="C")
    else:
        raise ValueError(f"unsupported data format: {fmt!r}")
    if array.dtype.kind != "f" or array.dtype.itemsize not in (4, 8):
        raise ValueError("only float32 and float64 arrays are supported")
    if not array.dtype.isnative:
        raise ValueError("non-native endian data is not supported; convert it explicitly")
    if array.size == 0 or not np.isfinite(array).all():
        raise ValueError("arrays must be non-empty and contain only finite values")
    array = np.ascontiguousarray(array)
    digest = hashlib.sha256(memoryview(array).cast("B")).hexdigest()
    lo, hi = float(np.min(array)), float(np.max(array))
    if not math.isfinite(hi - lo):
        raise ValueError("data range overflowed float64")
    return array, {"name": spec["name"], "path": str(path), "format": fmt,
                   "shape": list(array.shape), "dtype": array.dtype.str,
                   "elements": int(array.size), "original_bytes": int(array.nbytes),
                   "min": lo, "max": hi, "value_range": hi - lo, "sha256_data": digest}
