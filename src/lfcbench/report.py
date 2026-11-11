"""Summarize JSONL trials without discarding failures."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import statistics

FIELDS = ["dataset", "compressor", "error_mode", "error_value", "options", "ok", "violation", "error",
          "median_ratio", "median_bits_per_value", "median_compress_mib_s", "median_decompress_mib_s", "median_rmse", "max_abs_error"]


def summarize(path: Path):
    groups = {}
    with path.open(encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {line_number}: {exc}") from exc
            req = record.get("error_request", {})
            key = (record.get("dataset", {}).get("name", "?"), record.get("compressor", "?"),
                   req.get("mode", "?"), req.get("value", "?"), json.dumps(record.get("options", {}), sort_keys=True))
            groups.setdefault(key, []).append(record)
    rows = []
    for key, records in sorted(groups.items(), key=lambda x: tuple(str(y) for y in x[0])):
        ok = [r["metrics"] for r in records if r.get("status") == "ok" and "metrics" in r]
        def median(field):
            return statistics.median(m[field] for m in ok) if ok else None
        row = dict(zip(FIELDS[:5], key))
        row.update({status: sum(r.get("status") == status for r in records) for status in ("ok", "violation", "error")})
        row.update({"median_ratio": median("compression_ratio"), "median_bits_per_value": median("bits_per_value"),
                    "median_compress_mib_s": median("compress_mib_per_second"),
                    "median_decompress_mib_s": median("decompress_mib_per_second"),
                    "median_rmse": median("rmse"),
                    "max_abs_error": max((m["max_abs_error"] for m in ok), default=None)})
        rows.append(row)
    return rows


def print_summary(rows):
    print("dataset | compressor | bound | ok/violation/error | ratio | comp MiB/s | decomp MiB/s | max error")
    for r in rows:
        def n(v):
            return "-" if v is None else f"{v:.4g}"
        print(f"{r['dataset']} | {r['compressor']} | {r['error_mode']}={r['error_value']} | "
              f"{r['ok']}/{r['violation']}/{r['error']} | {n(r['median_ratio'])} | "
              f"{n(r['median_compress_mib_s'])} | {n(r['median_decompress_mib_s'])} | {n(r['max_abs_error'])}")


def write_csv(rows, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
