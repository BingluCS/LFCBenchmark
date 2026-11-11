import json

import numpy as np
import pytest

from lfcbench import AbsoluteError, benchmark, register_metric
from lfcbench.metric_registry import MetricRegistry, _manual, validate_metric_specs
from lfcbench.registry import Registry
from lfcbench.runner import run_config


def test_custom_metric_timing_scope_and_readonly_inputs(monkeypatch):
    from lfcbench import runner
    calls = []
    clock = iter([100,200,300,500])
    monkeypatch.setattr(runner.time,"perf_counter_ns",lambda: next(clock))
    def score(a,b,*,tag):
        calls.append(tag)
        assert not a.flags.writeable and not b.flags.writeable
        return {"score":float(np.max(np.abs(a-b)))}
    register_metric("test.quality",score)
    try:
        data = np.arange(100,dtype=float)
        result = benchmark(data,compressor="identity",error=AbsoluteError(.01),
                           quality_metrics=[{"name":"test.quality","options":{"tag":"called"}}])
        assert calls == ["called"]
        assert result["metrics"]["compress_seconds"] == 100/1e9
        assert result["metrics"]["decompress_seconds"] == 200/1e9
        assert result["metrics"]["quality"]["test.quality"]["score"] == 0
        assert result["quality_metrics"] == [{"name":"test.quality","options":{"tag":"called"}}]
    finally:
        del _manual["test.quality"]


def test_metric_yaml_records_only_measured_trials(tmp_path):
    calls = []
    register_metric("test.yaml",lambda a,b: calls.append(1) or {"score":0})
    try:
        np.save(tmp_path/"a.npy",np.arange(81,dtype=np.float32).reshape(9,9))
        (tmp_path/"run.yaml").write_text("""
datasets: [{name: array, path: a.npy}]
compressors: [{name: identity}]
error_bounds: [{mode: abs, value: 0.001}]
warmups: 2
repetitions: 2
quality_metrics: [{name: test.yaml}]
""")
        output = tmp_path/"run.jsonl"
        assert run_config(tmp_path/"run.yaml",output,Registry())["ok"] == 2
        assert calls == [1,1]
        records = [json.loads(line) for line in output.read_text().splitlines()]
        assert all("test.yaml" in row["metrics"]["quality"] for row in records)
        assert all(row["quality_metrics"] == [{"name":"test.yaml"}] for row in records)
    finally:
        del _manual["test.yaml"]


def test_plugin_errors_and_registration_conflicts():
    with pytest.raises(ValueError):
        validate_metric_specs([{"name":"a"},{"name":"a"}])
    register_metric("test.invalid",lambda a,b:{"score":float("nan")})
    try:
        with pytest.raises(ValueError):
            register_metric("test.invalid",lambda a,b:{})
        with pytest.raises(ValueError):
            benchmark(np.arange(10,dtype=float),compressor="identity",error=AbsoluteError(1),quality_metrics=[{"name":"test.invalid"}])
    finally:
        del _manual["test.invalid"]


def test_installed_lfcquality_entry_point():
    pytest.importorskip("lfcquality")
    assert "lfcquality" in MetricRegistry().names()
    result = benchmark(np.arange(81,dtype=np.float32).reshape(9,9),compressor="identity",error=AbsoluteError(.01),
                       quality_metrics=[{"name":"lfcquality","options":{"threads":2,"metrics":["psnr","pcc"]}}])
    quality = result["metrics"]["quality"]["lfcquality"]["metrics"]
    assert quality["pcc"]["value"] == pytest.approx(1)
    assert quality["psnr"]["status"] == "positive_infinity"


def test_plugin_cannot_mutate_later_trial_options():
    options = {"lags":[1,2]}
    seen = []
    def plugin(a,b,*,lags):
        seen.append(list(lags))
        lags.append(99)
        return {"score":0}
    register_metric("test.options",plugin)
    try:
        data = np.arange(10,dtype=float)
        specs = [{"name":"test.options","options":options}]
        for _ in range(2):
            result = benchmark(data,compressor="identity",error=AbsoluteError(1),quality_metrics=specs)
            assert result["quality_metrics"] == [{"name":"test.options","options":{"lags":[1,2]}}]
        assert seen == [[1,2],[1,2]] and options == {"lags":[1,2]}
    finally:
        del _manual["test.options"]


@pytest.mark.parametrize("name", ["sz3", "zfp"])
@pytest.mark.parametrize("dtype", ["float32", "float64"])
def test_lfcquality_with_real_compressor(name, dtype):
    pytest.importorskip("lfcquality")
    pytest.importorskip("pysz" if name == "sz3" else "zfpy")
    x = np.linspace(-1,1,16**3,dtype=dtype).reshape(16,16,16)
    specs = [{"name":"lfcquality", "options":{"threads":1,"fft_threads":1,"ssim_window":7}}]
    result = benchmark(x,compressor=name,error=AbsoluteError(1e-3),quality_metrics=specs)
    metrics = result["metrics"]
    quality = metrics["quality"]["lfcquality"]["metrics"]
    assert result["status"] == "ok"
    assert {"psnr","ssim","pcc","error_autocorrelation","autocorrelation","spectral"} <= set(quality)
    assert quality["error"]["max_abs_error"] == pytest.approx(metrics["max_abs_error"],abs=1e-15)
    assert quality["error"]["rmse"] == pytest.approx(metrics["rmse"],rel=1e-12,abs=1e-15)
