"""Run a configuration and persist every trial as a JSON Lines record."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import time

import numpy as np
import yaml

from . import __version__
from .api import AbsoluteError, Capabilities, pack_artifact, unpack_artifact
from .datasets import load_dataset
from .metrics import evaluate
from .metric_registry import evaluate_registered, validate_metric_specs


def environment():
    cpu = platform.processor() or platform.machine()
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {"host": platform.node(), "platform": platform.platform(), "cpu": cpu,
            "python": platform.python_version(), "numpy": np.__version__, "lfcbenchmark": __version__,
            "thread_environment": {k: os.environ.get(k) for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")}}


def _positive_int(value, name, *, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, int) or value < (0 if allow_zero else 1):
        raise ValueError(f"{name} must be {'non-negative' if allow_zero else 'positive'} integer")
    return value


def load_config(path: Path) -> dict:
    config = yaml.safe_load(path.read_text())
    if not isinstance(config, dict):
        raise ValueError("experiment config must be a YAML mapping")
    allowed = {"datasets", "compressors", "error_bounds", "warmups", "repetitions", "seed", "quality_metrics"}
    if set(config) - allowed:
        raise ValueError(f"unknown config keys: {sorted(set(config) - allowed)}")
    for key in ("datasets", "compressors", "error_bounds"):
        if not isinstance(config.get(key), list) or not config[key] or not all(isinstance(x, dict) for x in config[key]):
            raise ValueError(f"{key} must be a non-empty list of mappings")
    for dataset in config["datasets"]:
        if not isinstance(dataset.get("name"), str) or not dataset["name"] or not isinstance(dataset.get("path"), str):
            raise ValueError("each dataset needs a non-empty name and a path")
    if len({d["name"] for d in config["datasets"]}) != len(config["datasets"]):
        raise ValueError("dataset names must be unique")
    for item in config["compressors"]:
        if set(item) - {"name", "options"} or not isinstance(item.get("name"), str) or not isinstance(item.get("options", {}), dict):
            raise ValueError("compressor requires name and optional options mapping")
        json.dumps(item, allow_nan=False)
    for error in config["error_bounds"]:
        if set(error) != {"mode", "value"} or error["mode"] not in ("abs", "range_relative"):
            raise ValueError("error bound needs mode abs or range_relative and value")
        value = float(error["value"])
        if not math.isfinite(value) or value <= 0:
            raise ValueError("error bound value must be finite and positive")
        error["value"] = value
    config["warmups"] = _positive_int(config.get("warmups", 1), "warmups", allow_zero=True)
    config["repetitions"] = _positive_int(config.get("repetitions", 3), "repetitions")
    config["seed"] = _positive_int(config.get("seed", 42), "seed", allow_zero=True)
    config["quality_metrics"] = validate_metric_specs(config.get("quality_metrics"))
    return config


def absolute_bound(spec, data_info):
    if spec["mode"] == "abs":
        return AbsoluteError(spec["value"])
    if data_info["value_range"] == 0:
        raise ValueError("range-relative bound is undefined for a constant field; use abs")
    return AbsoluteError(spec["value"] * data_info["value_range"])


def run_trial(registry, compressor_name, options, array, error, *, quality_metrics=None, metric_context=None):
    quality_metrics = validate_metric_specs(quality_metrics)
    if "grid" not in registry.describe(compressor_name)["data_models"]:
        raise ValueError(f"{compressor_name} is not registered for grid data")
    encoder = registry.create(compressor_name)
    caps = encoder.capabilities()
    if not isinstance(caps, Capabilities):
        raise TypeError("capabilities() must return Capabilities")
    if ("grid" not in caps.data_models or array.dtype.name not in caps.dtypes or array.ndim not in caps.dimensions
            or "cpu" not in caps.devices or "abs" not in caps.error_modes):
        raise ValueError(f"{compressor_name} does not support dtype={array.dtype.name}, ndim={array.ndim}, device=cpu, error=abs")
    info = encoder.version_info()
    # Protect the original from third-party adapters; copying is outside codec timing.
    working = array.copy(order="C")
    working.flags.writeable = False
    encoder.synchronize()
    t0 = time.perf_counter_ns()
    artifact = encoder.compress(working, error=error, options=dict(options))
    encoder.synchronize()
    compress_ns = time.perf_counter_ns() - t0
    if not np.array_equal(working, array):
        raise ValueError("compressor modified its input array")
    packed = pack_artifact(compressor_name, artifact)
    restored_name, restored = unpack_artifact(packed)
    if restored_name != compressor_name:
        raise ValueError("serialized compressor identity mismatch")
    # A new instance establishes that decoding does not rely on encoder state.
    decoder = registry.create(restored_name)
    decoder.synchronize()
    t0 = time.perf_counter_ns()
    reconstructed = decoder.decompress(restored)
    decoder.synchronize()
    decompress_ns = time.perf_counter_ns() - t0
    metrics = evaluate(array, reconstructed, error.value)
    cseconds = max(compress_ns, 1) / 1e9
    dseconds = max(decompress_ns, 1) / 1e9
    metrics.update({"payload_bytes": len(artifact.payload), "compressed_bytes": len(packed),
                    "compression_ratio": array.nbytes / len(packed),
                    "bits_per_value": len(packed) * 8 / array.size,
                    "compress_seconds": cseconds, "decompress_seconds": dseconds,
                    "compress_mib_per_second": array.nbytes / (1024**2) / cseconds,
                    "decompress_mib_per_second": array.nbytes / (1024**2) / dseconds})
    if quality_metrics:
        metrics["quality"] = evaluate_registered(array, reconstructed, quality_metrics, context=metric_context)
    return info, metrics


def run_config(path: Path, output: Path, registry):
    path = path.expanduser().resolve(strict=True)
    config = load_config(path)
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    config_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    env = environment()
    rng = random.Random(config["seed"])
    counts = {"ok": 0, "violation": 0, "error": 0}
    with output.open("x", encoding="utf-8") as stream:
        def write(record):
            counts[record["status"]] += 1
            record.update({"schema_version": 1, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                           "config_path": str(path), "config_sha256": config_sha, "environment": env})
            stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()

        for data_spec in config["datasets"]:
            try:
                array, data_info = load_dataset(data_spec, path.parent)
            except Exception as exc:
                write({"status": "error", "stage": "dataset", "dataset": {"name": data_spec.get("name"), "path": data_spec.get("path")},
                       "error_message": f"{type(exc).__name__}: {exc}"})
                print(f"ERROR dataset={data_spec.get('name')}: {exc}", flush=True)
                continue
            cases = [(codec, bound) for codec in config["compressors"] for bound in config["error_bounds"]]
            rng.shuffle(cases)
            for codec, bound in cases:
                name, options = codec["name"], codec.get("options", {})
                base = {"dataset": data_info, "compressor": name, "options": options,
                        "error_request": bound, "seed": config["seed"]}
                if config["quality_metrics"]:
                    base["quality_metrics"] = config["quality_metrics"]
                    base["metric_context"] = {"dataset":data_info["name"],"domain":data_info.get("domain"),
                                              "data_model":"grid","metadata":data_info.get("metadata",{})}
                try:
                    base["compressor_registration"] = registry.describe(name)
                    abs_error = absolute_bound(bound, data_info)
                    base["absolute_error_bound"] = abs_error.value
                    for _ in range(config["warmups"]):
                        _, warm_metrics = run_trial(registry, name, options, array, abs_error)
                        if not warm_metrics["bound_satisfied"]:
                            raise ValueError("warmup violated the error bound")
                except Exception as exc:
                    write({**base, "status": "error", "stage": "setup_or_warmup", "repeat": None,
                           "error_message": f"{type(exc).__name__}: {exc}"})
                    print(f"ERROR {data_info['name']} / {name} / {bound}: {exc}", flush=True)
                    continue
                for index in range(config["repetitions"]):
                    try:
                        info, metrics = run_trial(registry, name, options, array, abs_error, quality_metrics=config["quality_metrics"],
                                                  metric_context=base.get("metric_context"))
                        status = "ok" if metrics["bound_satisfied"] else "violation"
                        write({**base, "status": status, "stage": "measured", "repeat": index + 1,
                               "compressor_version": info, "metrics": metrics})
                        print(f"{status.upper()} {data_info['name']} / {name} / {bound['mode']}={bound['value']:g} "
                              f"[{index+1}/{config['repetitions']}] ratio={metrics['compression_ratio']:.3f} "
                              f"max_error={metrics['max_abs_error']:.3g}", flush=True)
                    except Exception as exc:
                        write({**base, "status": "error", "stage": "measured", "repeat": index + 1,
                               "error_message": f"{type(exc).__name__}: {exc}"})
                        print(f"ERROR {data_info['name']} / {name} / repeat {index+1}: {exc}", flush=True)
    return counts
