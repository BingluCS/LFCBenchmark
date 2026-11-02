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

ENTRY_POINT_GROUP = "lfcbenchmark.compressors"
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_manual: dict[str, Callable] = {}


def _check_name(name: str) -> None:
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError(f"invalid compressor name: {name!r}")


def register_compressor(name: str, factory=None):
    """Register a no-argument factory, directly or as a decorator.

    For CLI use put this call in an importable module and pass --plugin MODULE.
    """
    _check_name(name)
    def register(candidate):
        if not callable(candidate):
            raise TypeError("compressor factory must be callable")
        if name in _manual:
            raise ValueError(f"duplicate compressor registration: {name}")
        _manual[name] = candidate
        return candidate
    return register if factory is None else register(factory)


@dataclass(frozen=True)
class Registration:
    name: str
    origin: str
    loader: Callable


class Registry:
    def __init__(self):
        # Entry point discovery reads metadata only. Loading a selected plugin is lazy.
        from .compressors import IdentityCompressor, SZ3Compressor, ZFPCompressor
        self._items: dict[str, list[Registration]] = {}
        for name, factory in {"identity": IdentityCompressor, "sz3": SZ3Compressor, "zfp": ZFPCompressor}.items():
            self._add(Registration(name, "built-in", lambda f=factory: f))
        for name, factory in _manual.items():
            self._add(Registration(name, "local registration", lambda f=factory: f))
        for ep in entry_points(group=ENTRY_POINT_GROUP):
            self._add(Registration(ep.name, f"entry point: {ep.value}", ep.load))

    def _add(self, registration: Registration):
        _check_name(registration.name)
        self._items.setdefault(registration.name, []).append(registration)

    def names(self):
        return sorted(self._items)

    def origins(self, name):
        return [x.origin for x in self._items.get(name, ())]

    def create(self, name: str) -> Compressor:
        registrations = self._items.get(name, [])
        if not registrations:
            raise ValueError(f"unknown compressor {name!r}; available: {', '.join(self.names())}")
        if len(registrations) != 1:
            raise ValueError(f"duplicate compressor {name!r}: {', '.join(self.origins(name))}")
        factory = registrations[0].loader()
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
