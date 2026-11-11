"""Verify published rate–quality points against the underlying measurements."""
import csv
import hashlib
import json
import statistics
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "docs" / "data"
QUALITY = DATA / "quality"
pytestmark = pytest.mark.skipif(not (QUALITY / "rd_manifest.json").exists(), reason="quality figures are not present")


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_quality_curves_match_published_measurements():
    protocol = read_json(QUALITY / "rd_manifest.json")
    website = read_json(DATA / "results.json")["quality_rd"]
    audit = read_json(QUALITY / "audit.json")
    assert audit["complete"] and audit["actual_points"] == audit["expected_points"] == 3960
    assert audit["actual_cross_matrices"] == audit["expected_cross_matrices"] == 90
    assert protocol["bounds"] == [0.1, 0.01, 0.001, 0.0001, 0.00001]
    for key in ("figures", "bounds", "metrics", "cross_datasets", "full_range_figures", "zoomed_bit_rates"):
        assert website[key] == protocol[key]
    assert protocol["quality_points_sha256"] == hashlib.sha256((QUALITY / "points.csv").read_bytes()).hexdigest()
    assert protocol["baseline_summary_sha256"] == hashlib.sha256((DATA / "sdrbench" / "summary_by_field.csv").read_bytes()).hexdigest()

    quality = read_rows(QUALITY / "points.csv")
    performance = read_rows(DATA / "sdrbench" / "summary_by_field.csv")
    cross = read_rows(QUALITY / "cross_variable_summary.csv")
    key = lambda r: (r["dataset"], r["field"], r["codec"], float(r["alpha"]))
    baseline = {key(r): r for r in performance}
    assert len(baseline) == len(performance)
    by_case = {}
    fields = {d: set() for d in protocol["datasets"]}
    for row in quality:
        if row["suspected_fill_value"] == "True" or row["duplicate_of"]:
            continue
        fields[row["dataset"]].add(row["field"])
        by_case.setdefault((row["dataset"], row["codec"], float(row["alpha"])), []).append(row)
    assert {d: len(v) for d, v in fields.items()} == protocol["field_counts"]
    assert len(protocol["excluded_fields"]) == 13
    cross_by_case = {(r["dataset"], r["codec"], float(r["alpha"])): r for r in cross}
    assert len(cross_by_case) == len(cross)

    points = read_rows(QUALITY / "quality_rd_points.csv")
    assert len(points) == 1500
    seen = set()
    for point in points:
        case = (point["dataset"], point["codec"], float(point["alpha"]))
        metric = point["metric"]
        point_key = (metric, *case)
        assert point_key not in seen
        seen.add(point_key)
        spec = protocol["metrics"][metric]
        cohort = by_case[case]
        if spec.get("cross"):
            selected_fields = set(protocol["cross_fields"][case[0]])
            cohort = [r for r in cohort if r["field"] in selected_fields]
            assert {r["field"] for r in cohort} == selected_fields
            summary = cross_by_case[case]
            assert int(point["pairs"]) == int(summary["valid_pairs"]) == int(summary["total_pairs"])
            expected_value = float(summary[spec["column"]])
        else:
            assert {r["field"] for r in cohort} == fields[case[0]]
            values = [float(r[spec["column"]]) for r in cohort]
            if spec.get("transform") == "one_minus":
                values = [1 - value for value in values]
            expected_value = statistics.median(values)
            assert not point["pairs"]
        assert int(point["fields"]) == len(cohort)
        source = [baseline[key(r)] for r in cohort]
        expected_rate = 8 * sum(float(r["mean_compressed_bytes"]) for r in source) / sum(int(r["elements"]) for r in source)
        assert float(point["bits_per_value"]) == pytest.approx(expected_rate, rel=1e-12, abs=0)
        assert float(point["value"]) == pytest.approx(expected_value, rel=1e-12, abs=0)

    expected_figures = set()
    for metric, spec in protocol["metrics"].items():
        datasets = protocol["cross_datasets"] if spec.get("cross") else protocol["datasets"]
        expected_figures.add("datasets_" + metric)
        expected_figures.update(dataset + "_" + metric for dataset in datasets)
    assert len(expected_figures) == 71
    assert set(protocol["figures"]) == expected_figures
    for name in expected_figures:
        for suffix in (".png", ".pdf"):
            assert (QUALITY / "figures" / (name + suffix)).is_file()

    limits = protocol["zoomed_bit_rates"]
    assert set(limits) == {"ssim_rd", "pcc_rd"}
    full_figures = set()
    for metric, label in (("ssim_rd", "SSIM"), ("pcc_rd", "Pearson r")):
        spec = protocol["metrics"][metric]
        assert spec["label"] == label and spec["scale"] == "linear" and "plot_transform" not in spec
        assert set(limits[metric]) == set(protocol["datasets"])
        full_figures.add(f"datasets_{metric}_full")
        for dataset, rate_limit in limits[metric].items():
            full_figures.add(f"{dataset}_{metric}_full")
            curve_points = [p for p in points if (p["metric"], p["dataset"]) == (metric, dataset)]
            omitted = [p for p in curve_points if float(p["bits_per_value"]) > rate_limit]
            assert omitted and all(float(p["value"]) >= .999 for p in omitted)
            for codec in {p["codec"] for p in curve_points}:
                assert sum(p["codec"] == codec and float(p["bits_per_value"]) <= rate_limit for p in curve_points) >= 2
    assert set(protocol["full_range_figures"]) == full_figures
    for name in full_figures:
        for suffix in (".png", ".pdf"):
            assert (QUALITY / "figures" / (name + suffix)).is_file()
