"""Public API for the floating-point compression benchmark."""
__version__ = "0.1.0"

from .api import AbsoluteError, Capabilities, CompressedData, Compressor
from .registry import register_compressor
from .benchmark import benchmark

__all__ = ["AbsoluteError", "Capabilities", "CompressedData", "Compressor", "register_compressor", "benchmark"]
