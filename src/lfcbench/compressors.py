"""Built-in CPU adapters. Optional libraries are imported only when used."""
from __future__ import annotations

from importlib.metadata import version
import numpy as np

from .api import AbsoluteError, Capabilities, CompressedData, Compressor

CPU_CAPABILITIES = Capabilities(dtypes=("float32", "float64"), dimensions=(1, 2, 3))


def _no_options(options):
    if options:
        raise ValueError(f"unsupported options: {', '.join(sorted(options))}")


def _array_metadata(array):
    return {"dtype": array.dtype.str, "shape": list(array.shape), "order": "C"}


class IdentityCompressor(Compressor):
    """Uncompressed baseline, including shape/dtype metadata in reported size."""
    def capabilities(self):
        return CPU_CAPABILITIES

    def compress(self, array, *, error: AbsoluteError, options):
        _no_options(options)
        return CompressedData(array.tobytes(order="C"), _array_metadata(array))

    def decompress(self, artifact):
        return np.frombuffer(artifact.payload, dtype=np.dtype(artifact.metadata["dtype"])).copy().reshape(artifact.metadata["shape"])

    def version_info(self):
        return {"adapter": "0.1.0", "backend": "identity"}


class ZFPCompressor(Compressor):
    """ZFP fixed-accuracy CPU mode via zfpy."""
    def capabilities(self):
        return CPU_CAPABILITIES

    def compress(self, array, *, error: AbsoluteError, options):
        _no_options(options)
        import zfpy
        payload = zfpy.compress_numpy(array, tolerance=error.value, write_header=True)
        return CompressedData(bytes(payload), _array_metadata(array))

    def decompress(self, artifact):
        import zfpy
        return zfpy.decompress_numpy(artifact.payload)

    def version_info(self):
        import zfpy  # Verify the optional native extension can actually be imported.
        return {"adapter": "0.1.0", "zfpy": version("zfpy")}


class SZ3Compressor(Compressor):
    """SZ3 absolute-error CPU mode via the upstream pysz binding."""
    def capabilities(self):
        return CPU_CAPABILITIES

    def compress(self, array, *, error: AbsoluteError, options):
        _no_options(options)
        from pysz import sz, szConfig, szErrorBoundMode
        config = szConfig()
        config.errorBoundMode = szErrorBoundMode.ABS
        config.absErrorBound = error.value
        compressed, _ratio = sz.compress(array, config)
        return CompressedData(compressed.tobytes(), _array_metadata(array))

    def decompress(self, artifact):
        from pysz import sz
        raw = np.frombuffer(artifact.payload, dtype=np.uint8)
        array, _config = sz.decompress(raw, np.dtype(artifact.metadata["dtype"]), tuple(artifact.metadata["shape"]))
        return array

    def version_info(self):
        import pysz  # Verify the optional native extension can actually be imported.
        return {"adapter": "0.1.0", "pysz": version("pysz")}
