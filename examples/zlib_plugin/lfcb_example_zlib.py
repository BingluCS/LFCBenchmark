"""An independently installed plugin. This is a lossless example, not SZ3/ZFP."""
import zlib

import numpy as np
from lfcbench import Capabilities, CompressedData, Compressor


class ZlibCompressor(Compressor):
    def capabilities(self):
        return Capabilities(dtypes=("float32", "float64"), dimensions=(1, 2, 3))

    def compress(self, array, *, error, options):
        unknown = set(options) - {"level"}
        if unknown:
            raise ValueError(f"unknown zlib options: {sorted(unknown)}")
        level = options.get("level", 6)
        if not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= 9:
            raise ValueError("level must be an integer between 0 and 9")
        payload = zlib.compress(array.tobytes(order="C"), level)
        return CompressedData(payload, {"dtype": array.dtype.str, "shape": list(array.shape)})

    def decompress(self, artifact):
        raw = zlib.decompress(artifact.payload)
        return np.frombuffer(raw, dtype=np.dtype(artifact.metadata["dtype"])).copy().reshape(artifact.metadata["shape"])

    def version_info(self):
        return {"adapter": "0.1.0", "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION}
