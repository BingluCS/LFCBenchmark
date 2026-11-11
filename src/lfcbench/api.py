"""Version 1 of the compressor adapter protocol."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
import math
import struct
from typing import Any

import numpy as np

API_VERSION = 1
MAGIC = b"LFCB01\x00\x00"
MAX_HEADER = 16 * 1024 * 1024


@dataclass(frozen=True)
class AbsoluteError:
    value: float

    def __post_init__(self):
        if not math.isfinite(self.value) or self.value <= 0:
            raise ValueError("absolute error bound must be finite and positive")


@dataclass(frozen=True)
class Capabilities:
    dtypes: tuple[str, ...]
    dimensions: tuple[int, ...]
    devices: tuple[str, ...] = ("cpu",)
    error_modes: tuple[str, ...] = ("abs",)
    data_models: tuple[str, ...] = ("grid",)


@dataclass(frozen=True)
class CompressedData:
    payload: bytes
    metadata: dict[str, Any] = field(default_factory=dict)


class Compressor(ABC):
    """Stateless adapter contract. All decompression state belongs in CompressedData."""

    api_version = API_VERSION

    @abstractmethod
    def capabilities(self) -> Capabilities:
        pass

    @abstractmethod
    def compress(self, array: np.ndarray, *, error: AbsoluteError, options: dict) -> CompressedData:
        pass

    @abstractmethod
    def decompress(self, artifact: CompressedData) -> np.ndarray:
        pass

    def synchronize(self) -> None:
        """Wait for asynchronous work; CPU adapters use this no-op."""

    def version_info(self) -> dict[str, str]:
        return {}


def pack_artifact(name: str, artifact: CompressedData) -> bytes:
    if not isinstance(artifact, CompressedData):
        raise TypeError("compress() must return CompressedData")
    if not isinstance(artifact.payload, bytes):
        raise TypeError("CompressedData.payload must be bytes")
    header = json.dumps(
        {"compressor": name, "metadata": artifact.metadata},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    if len(header) > MAX_HEADER:
        raise ValueError("compressed metadata exceeds maximum header size")
    return MAGIC + struct.pack(">Q", len(header)) + header + artifact.payload


def unpack_artifact(data: bytes) -> tuple[str, CompressedData]:
    if not isinstance(data, bytes) or len(data) < 16 or data[:8] != MAGIC:
        raise ValueError("invalid compressed artifact header")
    header_size = struct.unpack(">Q", data[8:16])[0]
    if header_size > MAX_HEADER or 16 + header_size > len(data):
        raise ValueError("invalid compressed artifact metadata length")
    header = json.loads(data[16:16 + header_size])
    if not isinstance(header, dict) or not isinstance(header.get("compressor"), str) or not isinstance(header.get("metadata"), dict):
        raise ValueError("invalid compressed artifact metadata")
    return header["compressor"], CompressedData(data[16 + header_size:], header["metadata"])
