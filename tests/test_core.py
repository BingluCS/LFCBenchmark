import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from lfcbench import AbsoluteError, CompressedData, benchmark
from lfcbench.api import pack_artifact, unpack_artifact
from lfcbench.datasets import load_dataset
from lfcbench.metrics import evaluate
from lfcbench.registry import Registry, register_compressor
from lfcbench.runner import absolute_bound, load_config, run_config, run_trial
from lfcbench.compressors import IdentityCompressor


def test_artifact_preserves_metadata_and_rejects_truncation():
    raw = pack_artifact("example.codec", CompressedData(b"data", {"shape": [2, 2], "dtype": "<f4"}))
    name, restored = unpack_artifact(raw)
    assert name == "example.codec" and restored.payload == b"data" and restored.metadata["shape"] == [2, 2]
    assert len(raw) > len(restored.payload)
    with pytest.raises(ValueError):
        unpack_artifact(raw[:12])


def test_independent_metrics_detect_bound_violation():
    a = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    b = np.array([1.0, 2.01, 3.0], dtype=np.float32)
    result = evaluate(a, b, 0.001)
    assert not result["bound_satisfied"] and result["error_bound_violations"] == 1
    with pytest.raises(ValueError):
        evaluate(a, np.array([1.0, np.nan, 3.0], dtype=np.float32), 0.001)


def test_registration_and_collision():
    register_compressor("test.identity", IdentityCompressor)
    assert isinstance(Registry().create("test.identity"), IdentityCompressor)
    with pytest.raises(ValueError, match="duplicate"):
        register_compressor("test.identity", IdentityCompressor)
    register_compressor("identity", IdentityCompressor)
    with pytest.raises(ValueError, match="duplicate"):
        Registry().create("identity")
    # Avoid affecting later tests with the intentionally conflicting registration.
    from lfcbench import registry
    del registry._manual["identity"]
    del registry._manual["test.identity"]


def test_input_format_and_range_relative_bound(tmp_path):
    original = np.arange(24, dtype=np.float32).reshape(2, 3, 4)
    raw = tmp_path / "input.raw"
    raw.write_bytes(original.tobytes())
    spec = {"name": "field", "path": str(raw), "format": "raw", "dtype": "<f4", "shape": [2, 3, 4]}
    data, info = load_dataset(spec, tmp_path)
    assert np.array_equal(data, original)
    assert absolute_bound({"mode": "range_relative", "value": 0.01}, info).value == pytest.approx(0.23)
    spec["shape"] = [2, 3, 3]
    with pytest.raises(ValueError, match="size mismatch"):
        load_dataset(spec, tmp_path)
    with pytest.raises(ValueError, match="constant"):
        absolute_bound({"mode": "range_relative", "value": 0.01}, {"value_range": 0.0})


@pytest.mark.parametrize("name", ["identity", "sz3", "zfp"])
@pytest.mark.parametrize("dtype", ["float32", "float64"])
def test_real_cpu_compressors(name, dtype):
    if name == "sz3":
        pytest.importorskip("pysz")
    if name == "zfp":
        pytest.importorskip("zfpy")
    data = np.linspace(-1, 1, 8**3, dtype=dtype).reshape(8, 8, 8)
    _, metrics = run_trial(Registry(), name, {}, data, AbsoluteError(1e-3))
    assert metrics["bound_satisfied"]
    assert metrics["compressed_bytes"] > metrics["payload_bytes"]
    assert metrics["compress_seconds"] > 0 and metrics["decompress_seconds"] > 0


def test_config_run_writes_each_repeat_and_never_overwrites(tmp_path):
    data = np.linspace(-1, 1, 64, dtype=np.float32).reshape(8, 8)
    np.save(tmp_path / "array.npy", data)
    config = tmp_path / "run.yaml"
    config.write_text("""
datasets:
  - name: example
    path: array.npy
compressors:
  - name: identity
error_bounds:
  - mode: abs
    value: 0.001
warmups: 1
repetitions: 2
""")
    output = tmp_path / "results.jsonl"
    counts = run_config(config, output, Registry())
    records = [json.loads(s) for s in output.read_text().splitlines()]
    assert counts == {"ok": 2, "violation": 0, "error": 0}
    assert len(records) == 2 and all(r["metrics"]["bound_satisfied"] for r in records)
    with pytest.raises(FileExistsError):
        run_config(config, output, Registry())


def test_invalid_config_is_rejected(tmp_path):
    path = tmp_path / "broken.yaml"
    path.write_text("datasets: []\ncompressors: []\nerror_bounds: []\n")
    with pytest.raises(ValueError):
        load_config(path)


def test_cli_imports_plugin_from_current_directory(tmp_path):
    (tmp_path / "custom_local.py").write_text(
        "from lfcbench import register_compressor\n"
        "from lfcbench.compressors import IdentityCompressor\n"
        "register_compressor('tests.local_copy', IdentityCompressor)\n"
    )
    proc = subprocess.run(
        [str(Path(sys.executable).parent / "lfcbench"), "--plugin", "custom_local", "list"],
        cwd=tmp_path, text=True, capture_output=True, check=True,
    )
    assert "tests.local_copy\tavailable" in proc.stdout


def test_python_api_accepts_manually_registered_compressor():
    register_compressor("test.python_api", IdentityCompressor)
    try:
        array = np.arange(12, dtype=np.float32).reshape(3, 4)
        result = benchmark(array, compressor="test.python_api", error=AbsoluteError(1e-3))
        assert result["status"] == "ok" and result["metrics"]["max_abs_error"] == 0
        assert result["shape"] == [3, 4]
    finally:
        from lfcbench import registry
        del registry._manual["test.python_api"]


def test_plot_handles_lossless_zero_error(tmp_path):
    pytest.importorskip("matplotlib")
    from lfcbench.plotting import plot_results
    np.save(tmp_path / "array.npy", np.arange(64, dtype=np.float32).reshape(8, 8))
    config = tmp_path / "plot.yaml"
    config.write_text("""
datasets:
  - name: zero-error
    path: array.npy
compressors:
  - name: identity
error_bounds:
  - mode: abs
    value: 0.001
warmups: 0
repetitions: 1
""")
    result_file = tmp_path / "run.jsonl"
    run_config(config, result_file, Registry())
    files = plot_results(result_file, tmp_path / "plots")
    assert len(files) == 1 and files[0].read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(FileExistsError):
        plot_results(result_file, tmp_path / "plots")
