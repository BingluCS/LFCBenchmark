"""Typed, extensible metadata for compressor and metric plugins."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re

TRACKS = ("general", "domain_specific", "particle")
DATA_MODELS = ("grid", "particles", "catalog")
_TAG = re.compile(r"^[a-z][a-z0-9_.-]*$")


def _tags(value, name, allowed=None):
    if isinstance(value, str) or not isinstance(value, (tuple, list)):
        raise TypeError(f"{name} must be a sequence of strings")
    result = tuple(value)
    if len(set(result)) != len(result) or any(not isinstance(x, str) or not _TAG.fullmatch(x) for x in result):
        raise ValueError(f"invalid or duplicate {name}: {result!r}")
    if allowed is not None and any(x not in allowed for x in result):
        raise ValueError(f"unsupported {name}: {result!r}")
    return result


@dataclass(frozen=True)
class PluginMetadata:
    """Tracks are not exclusive: e.g. a cosmology particle plugin uses two."""

    tracks: tuple[str, ...] = ("general",)
    data_models: tuple[str, ...] = ("grid",)
    domains: tuple[str, ...] = ()
    description: str = ""
    needs_context: bool = False

    def __post_init__(self):
        object.__setattr__(self, "tracks", _tags(self.tracks, "tracks", TRACKS))
        object.__setattr__(self, "data_models", _tags(self.data_models, "data_models", DATA_MODELS))
        object.__setattr__(self, "domains", _tags(self.domains, "domains"))
        if not self.tracks or not self.data_models:
            raise ValueError("at least one track and data model are required")
        if not isinstance(self.description, str):
            raise TypeError("description must be a string")
        if not isinstance(self.needs_context, bool):
            raise TypeError("needs_context must be boolean")

    def as_dict(self):
        return asdict(self)


def plugin_metadata(*, tracks=("general",), data_models=("grid",), domains=(), description="", needs_context=False):
    """Attach discoverable metadata to an installed entry-point plugin.

    Use this decorator on the exported factory/function without registering it
    locally; entry-point discovery performs registration when the package loads.
    """
    metadata = PluginMetadata(tracks=tracks, data_models=data_models, domains=domains, description=description,
                              needs_context=needs_context)
    def decorate(candidate):
        if not callable(candidate):
            raise TypeError("plugin must be callable")
        candidate.lfcbenchmark_metadata = metadata
        return candidate
    return decorate


def metadata_for(candidate):
    metadata = getattr(candidate, "lfcbenchmark_metadata", None)
    if metadata is None:
        return PluginMetadata()
    if not isinstance(metadata, PluginMetadata):
        raise TypeError("lfcbenchmark_metadata must be a PluginMetadata instance")
    return metadata
