#!/usr/bin/env python3
"""Export audited benchmark artifacts to the public GitHub Pages directory."""
import argparse
import csv
import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path

MEASUREMENT_COLUMNS = (
    "dataset", "field", "dtype", "shape", "codec", "alpha", "repeat", "warmup",
    "original_bytes", "compressed_bytes", "compress_seconds", "decompress_seconds",
    "absolute_bound", "effective_bound", "max_abs_error", "rmse", "nrmse", "psnr_db",
    "violations", "status", "reused",
)


def read_json(path):
    return json.loads(path.read_text())


def export_run(run, plots, output, name):
    audit = read_json(run / "audit.json")
    config = read_json(run / "config.json")
    metadata = read_json(run / "metadata.json")
    if audit["status"] != "ok" or audit["strict_bound_violations"] or audit["max_observed_threads"] != 1:
        raise ValueError(f"Expected a completed and verified single-thread run: {run}")

    output.mkdir(parents=True, exist_ok=True)
    for filename in ("summary_by_dataset.csv", "summary_by_field.csv", "summary_overall.csv",
                     "pareto_1e-3.csv", "timing_quality.json", "timing_variability.csv", "plot_metadata.json"):
        if (plots / filename).exists():
            (output / filename).write_text((plots / filename).read_text())

    figures = output / "figures"
    figures.mkdir(exist_ok=True)
    for path in sorted((plots / "figures").iterdir()):
        if path.suffix in (".png", ".pdf"):
            shutil.copyfile(path, figures / path.name)

    # Keep the measured revision available even when the public repository's
    # history differs from the server checkout used for the original run.
    source_bundle = run / "lfcbenchmark-source.bundle"
    if not source_bundle.is_file():
        raise ValueError(f"Audited native source bundle is missing: {source_bundle}")
    shutil.copyfile(source_bundle, output / "native-source.bundle")

    measurements = io.StringIO(newline="")
    writer = csv.DictWriter(measurements, MEASUREMENT_COLUMNS)
    writer.writeheader()
    formal = warmups = 0
    for field in config["fields"]:
        for codec in config["codecs"]:
            path = run / field["dataset"] / (field["field"] + "__" + codec + ".jsonl")
            with path.open() as handle:
                for line in handle:
                    row = json.loads(line)
                    if row["status"] != "ok" or row["violations"]:
                        raise ValueError(f"Unaudited measurement: {path.name}")
                    formal += not row["warmup"]
                    warmups += row["warmup"]
                    safe_row = {key: row.get(key) for key in MEASUREMENT_COLUMNS}
                    safe_row["shape"] = " × ".join(map(str, row["shape"]))
                    writer.writerow(safe_row)
    if (formal, warmups) != (audit["measured_records"], audit["warmup_records"]):
        raise ValueError(f"Audit totals disagree with raw measurements: {run}")
    with zipfile.ZipFile(output / "measurements.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("measurements.csv", measurements.getvalue())

    report = {
        "name": name,
        "repetitions": config["repetitions"],
        "warmups_per_point": config["warmups"],
        "fields": audit["tested_fields"],
        "jobs": audit["jobs"],
        "measurements": formal,
        "warmups": warmups,
        "max_threads": audit["max_observed_threads"],
        "strict_bound_violations": audit["strict_bound_violations"],
        "input_hashes_rechecked": audit["inputs_rehashed"],
        "excluded_fields": [{"dataset": row["dataset"], "field": row["field"], "reason": row["reason"]}
                            for row in audit["excluded_fields"]],
        "rounding_adjustments": audit.get("rounding_adjusted_configurations", []),
        "cpu": metadata["cpuinfo"].strip(),
        "timing_scope": metadata["timing_scope"],
        "native_benchmark_revision": audit["project_commit"],
    }
    (output / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    with (output / "summary_by_dataset.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    number_keys = ("alpha", "ratio", "bits_per_value", "psnr_db", "compress_MiB_s", "decompress_MiB_s")
    table = []
    for row in rows:
        point = {key: row[key] for key in ("dataset", "dtype", "codec")}
        point["fields"] = int(row["fields"])
        point.update({key: float(row[key]) if row[key] else None for key in number_keys})
        table.append(point)
    return {**report, "datasets": config["datasets"], "bounds": config["alphas"], "table": table,
            "figures": sorted(path.stem for path in figures.glob("*.png"))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdrbench", type=Path, required=True)
    parser.add_argument("--sdrbench-plots", type=Path, required=True)
    parser.add_argument("--python-smoke", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("docs/data"))
    args = parser.parse_args()
    output = args.output
    report = export_run(args.sdrbench, args.sdrbench_plots, output / "sdrbench", "SDRBench")
    lock = read_json(args.sdrbench / "sources.lock.json")
    manifest = {
        "sdrbench": report,
        "backends": {key: {"url": value["url"].removesuffix(".git"), "commit": value["commit"]}
                     for key, value in lock.items()},
    }
    quality_manifest = output / "quality" / "rd_manifest.json"
    if quality_manifest.is_file():
        quality = read_json(quality_manifest)
        sources = ((output / "quality" / "points.csv", "quality_points_sha256"),
                   (output / "sdrbench" / "summary_by_field.csv", "baseline_summary_sha256"))
        for source, key in sources:
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != quality.get(key):
                raise ValueError(f"Quality figures do not match {source}; regenerate them before exporting")
        manifest["quality_rd"] = {key: quality[key] for key in ("figures", "bounds", "metrics", "cross_datasets",
                                                                "full_range_figures", "zoomed_bit_rates")}
    (output / "results.json").write_text(json.dumps(manifest, separators=(",", ":"), allow_nan=False) + "\n")
    smoke = output / "python-smoke"
    smoke.mkdir(exist_ok=True)
    for filename in ("server-summary.csv", "plugin-validation.csv"):
        (smoke / filename).write_text((args.python_smoke / filename).read_text())
    for folder in ("figures", "plugin-figures"):
        for path in sorted((args.python_smoke / folder).glob("*.png")):
            shutil.copyfile(path, smoke / (("plugin-" if folder == "plugin-figures" else "") + path.name))
    alt = args.sdrbench_plots.parent / "hurricane-log-preferred"
    if alt.is_dir():
        with zipfile.ZipFile(output / "sdrbench" / "hurricane-log-preferred.zip", "w",
                             compression=zipfile.ZIP_DEFLATED) as archive:
            for filename in ("summary_by_dataset.csv", "summary_overall.csv", "pareto_1e-3.csv", "plot_metadata.json"):
                archive.write(alt / filename, filename)
            for path in sorted((alt / "figures").glob("*.pdf")):
                archive.write(path, "figures/" + path.name)


if __name__ == "__main__":
    main()
