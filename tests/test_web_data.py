"""Check published measurements and figures against their audit metadata."""
from collections import Counter
import csv
import io
import json
from pathlib import Path
import subprocess
import tarfile
import zipfile

import pytest

DATA = Path(__file__).resolve().parents[1] / "docs" / "data"
pytestmark = pytest.mark.skipif(not (DATA / "results.json").exists(), reason="website data is not present")


def read_json(path):
    return json.loads(path.read_text())


def test_measurements_match_audit_and_manifest():
    run = read_json(DATA / "results.json")["sdrbench"]
    audit = read_json(DATA / "sdrbench" / "audit.json")
    assert audit["strict_bound_violations"] == 0
    assert audit["max_threads"] == 1
    assert audit["input_hashes_rechecked"]
    assert audit["fields"] == run["fields"]
    codecs = set(read_json(DATA / "results.json")["backends"])
    counts, warmups, fields = Counter(), Counter(), set()
    with zipfile.ZipFile(DATA / "sdrbench" / "measurements.zip") as archive:
        with archive.open("measurements.csv") as raw:
            for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8")):
                assert row["status"] == "ok" and int(row["violations"]) == 0
                key = (row["dataset"], row["field"], row["codec"], float(row["alpha"]))
                assert row["dataset"] in run["datasets"] and row["codec"] in codecs
                assert float(row["alpha"]) in run["bounds"]
                fields.add(key[:2])
                if row["warmup"] == "True":
                    warmups[key] += 1
                else:
                    assert row["warmup"] == "False"
                    counts[key] += 1
    assert len(fields) == audit["fields"]
    assert len(counts) == len(fields)*len(codecs)*len(run["bounds"])
    assert set(counts.values()) == {audit["repetitions"]}
    if audit["warmups_per_point"]:
        assert set(warmups) == set(counts)
        assert set(warmups.values()) == {audit["warmups_per_point"]}
    else:
        assert not warmups
    assert sum(counts.values()) == audit["measurements"] == run["measurements"]
    assert sum(warmups.values()) == audit["warmups"]


def test_figure_metadata_and_hurricane_alternative_match_run():
    run = read_json(DATA / "results.json")["sdrbench"]
    metadata = read_json(DATA / "sdrbench" / "plot_metadata.json")
    assert metadata["repetitions"] == run["repetitions"]
    assert metadata["throughput_units"] == "MiB/s (1 MiB = 1048576 bytes)"
    assert metadata["rd_figure_bounds"] == [0.1,0.01,0.001,0.0001,0.00001]
    assert metadata["throughput_figure_bounds"] == [0.01,0.001,0.0001,0.00001]
    assert metadata["pareto_figure_bound"] == 0.001
    with zipfile.ZipFile(DATA / "sdrbench" / "hurricane-log-preferred.zip") as archive:
        alternative = json.loads(archive.read("plot_metadata.json"))
    assert alternative["repetitions"] == run["repetitions"]
    assert alternative["hurricane_aggregation"] != metadata["hurricane_aggregation"]
    for name in run["figures"]:
        for suffix in (".png", ".pdf"):
            assert (DATA / "sdrbench" / "figures" / (name+suffix)).is_file()


def test_web_table_matches_exported_dataset_csv():
    run = read_json(DATA / "results.json")["sdrbench"]
    with (DATA / "sdrbench" / "summary_by_dataset.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(run["table"]) == len(rows)
    csv_rows = {(r["dataset"],r["codec"],float(r["alpha"])):r for r in rows}
    for point in run["table"]:
        row = csv_rows[(point["dataset"],point["codec"],point["alpha"])]
        for key in ("ratio","bits_per_value","psnr_db","compress_MiB_s","decompress_MiB_s"):
            if row[key]:
                assert point[key] == pytest.approx(float(row[key]))
            else:
                assert point[key] is None


def test_throughput_summaries_use_binary_mebibytes():
    with (DATA / "sdrbench" / "summary_by_field.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            for phase in ("compress", "decompress"):
                expected = int(row["original_bytes"]) / (1024**2) / float(row["mean_" + phase + "_seconds"])
                assert float(row[phase + "_MiB_s"]) == pytest.approx(expected)


def test_native_bundle_contains_audited_source(tmp_path):
    audit = read_json(DATA / "sdrbench" / "audit.json")
    bundle = DATA / "sdrbench" / "native-source.bundle"
    checkout = tmp_path / "native-source"
    subprocess.run(["git","clone","--quiet",str(bundle),str(checkout)],check=True)
    revision = audit["native_benchmark_revision"]
    tar = subprocess.run(["git","-C",str(checkout),"archive",revision,"native","native_typed"],
                         check=True,capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as archive:
        files = {item.name for item in archive if item.isfile() and archive.extractfile(item).read()}
    assert any(name.startswith("native/") for name in files)
    assert any(name.startswith("native_typed/") for name in files)
