"""Command line entry points."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

import numpy as np

from .api import AbsoluteError
from .registry import Registry, import_local_plugins
from .report import print_summary, summarize, write_csv
from .runner import run_config, run_trial


def parser():
    p = argparse.ArgumentParser(prog="lfcbench", description="Error-bounded floating-point compression benchmark")
    p.add_argument("--plugin", action="append", default=[], metavar="MODULE", help="import a local module that registers compressors; can repeat")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list registered compressors and availability")
    inspect = sub.add_parser("inspect", help="show the capabilities of a compressor")
    inspect.add_argument("name")
    validate = sub.add_parser("validate", help="run small round-trip and error-bound checks")
    validate.add_argument("name")
    run = sub.add_parser("run", help="run a YAML experiment")
    run.add_argument("config", type=Path)
    run.add_argument("--output", "-o", type=Path, required=True, help="new JSONL results file; will not overwrite")
    report = sub.add_parser("report", help="summarize a JSONL results file")
    report.add_argument("results", type=Path)
    report.add_argument("--csv", type=Path, help="write a new CSV file; will not overwrite")
    plot = sub.add_parser("plot", help="write per-dataset trade-off plots")
    plot.add_argument("results", type=Path)
    plot.add_argument("--output-dir", type=Path, required=True, help="directory for new PNG figures")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        import_local_plugins(args.plugin)
        registry = Registry()
        if args.command == "list":
            for name in registry.names():
                try:
                    obj = registry.create(name)
                    info = obj.version_info()
                    print(f"{name}\tavailable\t{', '.join(registry.origins(name))}\t{json.dumps(info, sort_keys=True)}")
                except Exception as exc:
                    print(f"{name}\tunavailable\t{', '.join(registry.origins(name))}\t{type(exc).__name__}: {exc}")
            return 0
        if args.command == "inspect":
            obj = registry.create(args.name)
            print(json.dumps({"name": args.name, "origins": registry.origins(args.name), "api_version": obj.api_version,
                              "capabilities": asdict(obj.capabilities()), "version": obj.version_info()}, indent=2))
            return 0
        if args.command == "validate":
            obj = registry.create(args.name)
            caps = obj.capabilities()
            checked = 0
            for dtype in ("float32", "float64"):
                for ndim in (1, 2, 3):
                    if dtype not in caps.dtypes or ndim not in caps.dimensions or "cpu" not in caps.devices or "abs" not in caps.error_modes:
                        continue
                    shape = (8,) * ndim
                    array = np.linspace(-1, 1, num=8**ndim, dtype=dtype).reshape(shape)
                    _, metrics = run_trial(registry, args.name, {}, array, AbsoluteError(1e-3))
                    if not metrics["bound_satisfied"]:
                        raise ValueError(f"error bound violated for {dtype}, {ndim}D: {metrics['max_abs_error']}")
                    print(f"PASS {args.name} {dtype} {ndim}D max_abs_error={metrics['max_abs_error']:.3g}")
                    checked += 1
            if not checked:
                raise ValueError("no supported CPU/absolute-error combinations to validate")
            return 0
        if args.command == "run":
            counts = run_config(args.config, args.output, registry)
            print(f"Results: {args.output} | ok={counts['ok']} violation={counts['violation']} error={counts['error']}")
            return 0 if counts["ok"] > 0 and not (counts["violation"] or counts["error"]) else 1
        if args.command == "report":
            rows = summarize(args.results)
            print_summary(rows)
            if args.csv:
                write_csv(rows, args.csv)
            return 0
        if args.command == "plot":
            from .plotting import plot_results
            for output in plot_results(args.results, args.output_dir):
                print(f"Wrote {output}")
            return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(f"lfcbench: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
