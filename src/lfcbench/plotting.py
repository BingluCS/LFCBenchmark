"""Generate per-dataset trade-off figures from successful trial medians."""
from __future__ import annotations

from collections import defaultdict
import hashlib
from pathlib import Path
import re

from .report import summarize


def plot_results(results: Path, output_dir: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = [r for r in summarize(results) if r["ok"]]
    if not rows:
        raise ValueError("results contain no successful trials to plot")
    datasets = defaultdict(list)
    for row in rows:
        datasets[row["dataset"]].append(row)
    planned = []
    for name in sorted(datasets):
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")[:60] or "dataset"
        suffix = hashlib.sha256(name.encode()).hexdigest()[:8]
        planned.append((name, output_dir / f"{slug}-{suffix}.png"))
    output_dir.mkdir(parents=True, exist_ok=True)
    exists = [str(path) for _, path in planned if path.exists()]
    if exists:
        raise FileExistsError(f"plot output already exists: {', '.join(exists)}")
    for name, path in planned:
        series = defaultdict(list)
        for row in datasets[name]:
            key = (row["compressor"], row["error_mode"], row["options"])
            series[key].append(row)
        fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), constrained_layout=True)
        fig.suptitle(name + " — median of valid repeats", fontsize=13)
        zero_rmse = 0
        for series_index, ((codec, mode, options), items) in enumerate(sorted(series.items())):
            label = f"{codec} ({mode})" + (f" {options}" if options != "{}" else "")
            color = plt.get_cmap("tab10")(series_index % 10)
            rd = sorted((r for r in items if r["median_rmse"] > 0), key=lambda r: r["median_bits_per_value"])
            zero_rmse += sum(r["median_rmse"] == 0 for r in items)
            if rd:
                axes[0].plot([r["median_bits_per_value"] for r in rd], [r["median_rmse"] for r in rd], marker="o", color=color, label=label)
            speed = sorted(items, key=lambda r: r["median_ratio"])
            axes[1].plot([r["median_ratio"] for r in speed], [r["median_compress_mib_s"] for r in speed], marker="o", color=color, label=label)
            axes[2].plot([r["median_ratio"] for r in speed], [r["median_decompress_mib_s"] for r in speed], marker="o", color=color, label=label)
        axes[0].set(xlabel="Compressed bits / value", ylabel="RMSE", title="Rate–distortion")
        if any(r["median_rmse"] > 0 for r in datasets[name]):
            axes[0].set_yscale("log")
        if zero_rmse:
            axes[0].text(0.02, 0.02, f"{zero_rmse} zero-RMSE point(s) omitted", transform=axes[0].transAxes, fontsize=8)
        axes[1].set(xlabel="Compression ratio", ylabel="MiB/s", title="Compression")
        axes[2].set(xlabel="Compression ratio", ylabel="MiB/s", title="Decompression")
        for ax in axes:
            ax.grid(True, alpha=0.25)
        axes[2].legend(fontsize=8, loc="best")
        fig.savefig(path, dpi=160)
        plt.close(fig)
    return [path for _, path in planned]
