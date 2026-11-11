"""Exercise the public leaderboard build and complete-cohort checks."""
import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_published_leaderboard_rebuilds_from_tracked_inputs(tmp_path):
    output = tmp_path / "leaderboard.json"
    subprocess.run([sys.executable, str(ROOT / "scripts/export_leaderboard.py"), "--output", str(output)],
                   cwd=ROOT, check=True)
    rebuilt = json.loads(output.read_text())
    published = json.loads((ROOT / "docs/data/leaderboard.json").read_text())

    def compare(actual, expected):
        if isinstance(expected, float):
            # Python versions can sum the same decimal input with a one-ULP difference.
            assert actual == pytest.approx(expected, rel=1e-12, abs=1e-30)
        elif isinstance(expected, dict):
            assert actual.keys() == expected.keys()
            for key in expected:
                compare(actual[key], expected[key])
        elif isinstance(expected, list):
            assert len(actual) == len(expected)
            for left, right in zip(actual, expected):
                compare(left, right)
        else:
            assert actual == expected

    compare(rebuilt, published)


def test_new_codec_requires_complete_comparable_field_cohort(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("board_export", ROOT / "scripts/export_leaderboard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    data = tmp_path / "docs/data"
    quality = data / "quality"
    (data / "sdrbench").mkdir(parents=True)
    quality.mkdir()
    (data / "sdrbench/audit.json").write_text(json.dumps({
        "strict_bound_violations": 0, "max_threads": 1, "input_hashes_rechecked": True, "cpu": "Test CPU"}))
    (data / "results.json").write_text(json.dumps({"backends": {
        name: {"url": "https://github.com/example/" + name, "commit": "a" * 40}
        for name in ("ZFP", "example")}}))
    (quality / "config.json").write_text(json.dumps({
        "compression_threads": 1, "error_mode": "alpha * (max(original)-min(original))",
        "alphas": [0.001], "codecs": ["ZFP", "example"], "metric_options": {},
        "fields": [{"dataset": "NYX", "field": field} for field in ("density", "temperature")]}))

    def write_rows(path, rows):
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    def prepare(incomplete=False):
        performance, quality_rows = [], []
        for codec in ("ZFP", "example"):
            for field in ("density", "temperature"):
                if incomplete and codec == "example" and field == "temperature":
                    continue
                identity = {"dataset": "NYX", "field": field, "codec": codec, "alpha": 0.001}
                performance.append(identity | {"original_bytes": 16, "mean_compressed_bytes": 8,
                    "elements": 4, "mean_compress_seconds": 0.2, "mean_decompress_seconds": 0.1,
                    "nrmse": 0.01, "ratio": 2})
                quality_rows.append(identity | {"verification": "ok", "suspected_fill_value": "False",
                    "duplicate_of": "", "ratio": 2, "nrmse": 0.01,
                    "input_sha256": ("a" if field == "density" else "b") * 64,
                    "ssim": 0.9, "pcc": 0.9, "power_relative_l1": 0.1, "field_acf_mean_abs_delta": 0.01})
        write_rows(data / "sdrbench/summary_by_field.csv", performance)
        write_rows(quality / "points.csv", quality_rows)
        (quality / "audit.json").write_text(json.dumps({"complete": True, "error_count": 0,
            "expected_points": len(quality_rows), "actual_points": len(quality_rows)}))

    prepare()
    output = tmp_path / "board.json"
    module.export(quality, output)
    group = json.loads(output.read_text())["groups"][0]
    assert {entry["codec"] for entry in group["entries"]} == {"ZFP", "example"}
    prepare(incomplete=True)
    with pytest.raises(ValueError, match="incomplete matched cohort"):
        module.export(quality, output)
