"""Optional post-decode metrics, registered locally or by installed entry points."""
from __future__ import annotations

from copy import deepcopy
from importlib.metadata import entry_points
import json
import re
from .plugin_metadata import PluginMetadata, metadata_for

ENTRY_POINT_GROUP = "lfcbenchmark.metrics"
_manual = {}
_manual_metadata = {}


def _check_name(name):
    if not isinstance(name,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*",name):
        raise ValueError(f"invalid metric name: {name!r}")


def register_metric(name, function=None, *, tracks=None, data_models=None, domains=None,
                    description=None, needs_context=None):
    """Register fn(original, reconstructed, **options) -> JSON-compatible dict.

    Functions are invoked after compression/decompression timers have stopped.
    Inputs are read-only NumPy views. Registration works directly or as a decorator.
    """
    _check_name(name)
    def register(candidate):
        if not callable(candidate):
            raise TypeError("metric must be callable")
        if name in _manual:
            raise ValueError(f"duplicate metric registration: {name}")
        inherited = metadata_for(candidate)
        _manual_metadata[name] = PluginMetadata(
            tracks=inherited.tracks if tracks is None else tracks,
            data_models=inherited.data_models if data_models is None else data_models,
            domains=inherited.domains if domains is None else domains,
            description=inherited.description if description is None else description,
            needs_context=inherited.needs_context if needs_context is None else needs_context,
        )
        _manual[name] = candidate
        return candidate
    return register if function is None else register(function)


def unregister_metric(name):
    """Remove a local metric; installed entry points remain available."""
    _check_name(name)
    if name not in _manual:raise ValueError(f"no local metric registration: {name}")
    del _manual[name]
    _manual_metadata.pop(name,None)


class MetricRegistry:
    def __init__(self):
        self._items = {}
        for name,function in _manual.items():
            self._items.setdefault(name,[]).append(("local registration",lambda f=function:f,_manual_metadata.get(name)))
        for ep in entry_points(group=ENTRY_POINT_GROUP):
            _check_name(ep.name)
            self._items.setdefault(ep.name,[]).append((f"entry point: {ep.value}",ep.load,None))

    def names(self):
        return sorted(self._items)

    def origins(self,name):
        return [item[0] for item in self._items.get(name,())]

    def _resolve(self,name):
        items = self._items.get(name,())
        if not items:
            raise ValueError(f"unknown metric {name!r}; available: {', '.join(self.names())}")
        if len(items) != 1:
            raise ValueError(f"duplicate metric {name!r}: {', '.join(self.origins(name))}")
        function = items[0][1]()
        if not callable(function):
            raise TypeError(f"metric {name!r} entry point must expose a callable")
        return function, items[0][2] or metadata_for(function)

    def get(self,name):
        return self._resolve(name)[0]

    def describe(self,name):
        _, metadata = self._resolve(name)
        return {"name":name,"origins":self.origins(name),**metadata.as_dict()}


def validate_metric_specs(specs):
    if specs is None:
        return []
    if not isinstance(specs,list):
        raise ValueError("quality_metrics must be a list of name/options mappings")
    names = set()
    for spec in specs:
        if not isinstance(spec,dict) or set(spec)-{"name","options"}:
            raise ValueError("each quality metric accepts name and optional options")
        name = spec.get("name")
        _check_name(name)
        if name in names:
            raise ValueError(f"duplicate quality metric: {name}")
        names.add(name)
        if not isinstance(spec.get("options",{}),dict):
            raise ValueError("quality metric options must be a mapping")
        json.dumps(spec,allow_nan=False)
    return specs


def evaluate_registered(original,reconstructed,specs, *, context=None):
    specs = validate_metric_specs(specs)
    registry, output = MetricRegistry(), {}
    data_model = "grid"
    a,b = original.view(), reconstructed.view()
    a.flags.writeable = b.flags.writeable = False
    if context is not None:
        if not isinstance(context, dict):
            raise TypeError("metric_context must be a JSON-compatible mapping")
        json.dumps(context, allow_nan=False)
        if context.get("data_model",data_model) != data_model:
            raise ValueError("metric_context data_model does not match the input")
    for spec in specs:
        # A plugin may modify a mutable option (for example, a list of lags).
        # Preserve the requested configuration for later trials and provenance.
        function, metadata = registry._resolve(spec["name"])
        if data_model not in metadata.data_models:
            raise ValueError(f"metric {spec['name']!r} does not support {data_model}")
        if metadata.domains and (context is None or context.get("domain") not in metadata.domains):
            raise ValueError(f"metric {spec['name']!r} requires one of domains {metadata.domains}")
        if metadata.needs_context and context is None:
            raise ValueError(f"metric {spec['name']!r} requires metric_context")
        options = deepcopy(spec.get("options",{}))
        if metadata.needs_context:
            if "context" in options:
                raise ValueError("metric option 'context' is reserved")
            options["context"] = deepcopy(context)
        value = function(a,b,**options)
        if not isinstance(value,dict):
            raise TypeError(f"metric {spec['name']!r} must return a dictionary")
        json.dumps(value,allow_nan=False)
        output[spec["name"]] = value
    return output
