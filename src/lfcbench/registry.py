"""Built-in, directly registered, and installed entry-point compressors."""
from __future__ import annotations

from dataclasses import dataclass
import importlib
from importlib.metadata import entry_points
from pathlib import Path
import re
import sys
from typing import Callable

from .api import API_VERSION, Compressor
from .plugin_metadata import PluginMetadata, metadata_for

ENTRY_POINT_GROUP = "lfcbenchmark.compressors"
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_manual: dict[str, Callable] = {}
_manual_metadata: dict[str, PluginMetadata] = {}


def _check_name(name: str) -> None:
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError(f"invalid compressor name: {name!r}")


def register_compressor(name: str, factory=None, *, tracks=None, data_models=None, domains=None, description=None):
    """Register a no-argument factory, directly or as a decorator.

    For CLI use put this call in an importable module and pass --plugin MODULE.
    """
    _check_name(name)
    def register(candidate):
        if not callable(candidate):
            raise TypeError("compressor factory must be callable")
        if name in _manual:
            raise ValueError(f"duplicate compressor registration: {name}")
        inherited = metadata_for(candidate)
        _manual_metadata[name] = PluginMetadata(
            tracks=inherited.tracks if tracks is None else tracks,
            data_models=inherited.data_models if data_models is None else data_models,
            domains=inherited.domains if domains is None else domains,
            description=inherited.description if description is None else description,
        )
        _manual[name] = candidate
        return candidate
    return register if factory is None else register(factory)


def unregister_compressor(name: str):
    """Remove a local registration; built-ins and installed entry points remain."""
    _check_name(name)
    if name not in _manual:raise ValueError(f"no local compressor registration: {name}")
    del _manual[name]
    _manual_metadata.pop(name,None)


@dataclass(frozen=True)
class Registration:
    name: str
    origin: str
    loader: Callable
    metadata: PluginMetadata | None = None


class Registry:
    def __init__(self):
        # Entry point discovery reads metadata only. Loading a selected plugin is lazy.
        from .compressors import IdentityCompressor, SZ3Compressor, ZFPCompressor
        self._items: dict[str, list[Registration]] = {}
        for name, factory in {"identity": IdentityCompressor, "sz3": SZ3Compressor, "zfp": ZFPCompressor}.items():
            self._add(Registration(name, "built-in", lambda f=factory: f))
        for name, factory in _manual.items():
            self._add(Registration(name, "local registration", lambda f=factory: f, _manual_metadata.get(name)))
        for ep in entry_points(group=ENTRY_POINT_GROUP):
            self._add(Registration(ep.name, f"entry point: {ep.value}", ep.load))

    def _add(self, registration: Registration):
        _check_name(registration.name)
        self._items.setdefault(registration.name, []).append(registration)

    def names(self):
        return sorted(self._items)

    def origins(self, name):
        return [x.origin for x in self._items.get(name, ())]

    def _resolve(self, name):
        registrations = self._items.get(name, [])
        if not registrations:
            raise ValueError(f"unknown compressor {name!r}; available: {', '.join(self.names())}")
        if len(registrations) != 1:
            raise ValueError(f"duplicate compressor {name!r}: {', '.join(self.origins(name))}")
        registration = registrations[0]
        factory = registration.loader()
        return factory, registration.metadata or metadata_for(factory)

    def describe(self, name):
        factory, metadata = self._resolve(name)
        return {"name": name, "origins": self.origins(name), **metadata.as_dict()}

    def create(self, name: str) -> Compressor:
        factory, metadata = self._resolve(name)
        instance = factory()
        if not isinstance(instance, Compressor):
            raise TypeError(f"{name}: factory must return a Compressor instance")
        if instance.api_version != API_VERSION:
            raise ValueError(f"{name}: incompatible adapter API version {instance.api_version!r}; expected {API_VERSION}")
        return instance


def import_local_plugins(modules: list[str]) -> None:
    # Console scripts start with their executable directory on sys.path, not
    # necessarily the caller's working directory. --plugin is an explicit
    # request to load local code, so make that directory importable.
    if modules and str(Path.cwd()) not in sys.path:
        sys.path.insert(0, str(Path.cwd()))
    for module in modules:
        importlib.import_module(module)
