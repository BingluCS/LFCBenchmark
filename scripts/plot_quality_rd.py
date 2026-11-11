#!/usr/bin/env python3
"""Produce audited post-analysis rate–distortion figures for GitHub Pages.

All validation and plotting are intended to run on HPDPS-8. Each curve joins
five audited configurations, from 1E-1 through 1E-5. Dataset-level quality is
the median over the same fields used to calculate the combined bit rate.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator, ScalarFormatter
from plot_panels import compact_axis, label_row, panel_row

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ("NYX", "Hurricane", "Miranda", "SCALE", "CESM", "JHTDB")
CROSS_DATASETS = ("NYX", "Hurricane", "Miranda")
CODECS = ("ZFP", "PFPL", "SPERR", "SZ3", "Falcons")
ALPHAS = (0.1, 0.01, 0.001, 0.0001, 0.00001)
SIMILARITY_METRICS = ("ssim_rd", "pcc_rd")
PLATEAU_SCORE = .999
COLORS = {"ZFP":"#3C4248", "PFPL":"#FB9700", "SPERR":"#93999F", "SZ3":"#1F77B4", "Falcons":"#D62728"}
MARKERS = {"ZFP":"s", "PFPL":"v", "SPERR":"o", "SZ3":"^", "Falcons":"D"}
LINES = {"ZFP":"-.", "PFPL":"--", "SPERR":":", "SZ3":"--", "Falcons":"-"}

# Keep raw field scores in the CSV.
METRICS = {
    "ssim_rd": {"label":"SSIM", "column":"ssim", "scale":"linear", "description":"Median field SSIM versus combined bits/value."},
    "ssim_loss_rd": {"label":"1 − SSIM", "column":"ssim", "transform":"one_minus", "scale":"log", "description":"Median 1−SSIM versus combined bits/value; smaller is better."},
    "pcc_rd": {"label":"Pearson r", "column":"pcc", "scale":"linear", "description":"Median Pearson correlation between original and reconstructed fields versus combined bits/value."},
    "nrmse_rd": {"label":"NRMSE", "column":"nrmse", "scale":"log", "description":"Median range-normalized RMSE versus combined bits/value. NRMSE and PSNR are mathematically related."},
    "spectral_l1_rd": {"label":"Relative spectral power L1", "column":"power_relative_l1", "scale":"log", "description":"Median full-grid relative spectral power L1 error versus combined bits/value; this is not fraction of energy lost."},
    "spectral_l2_rd": {"label":"Relative spectral power L2", "column":"power_relative_l2", "scale":"log", "description":"Median full-grid relative spectral power L2 error versus combined bits/value."},
    "fourier_l2_rd": {"label":"Relative Fourier L2", "column":"fourier_relative_l2", "scale":"log", "description":"Median phase-sensitive relative Fourier L2 versus combined bits/value; Parseval links it to spatial L2."},
    "field_acf_rd": {"label":"Mean |Δ field ACF|", "column":"field_acf_mean_abs_delta", "scale":"log", "description":"Median field ACF change averaged across axes and lags 1, 2, 4, 8, versus combined bits/value."},
    "error_acf_rd": {"label":"Mean |error ACF|", "column":"error_acf_mean_abs", "scale":"log", "description":"Median absolute error ACF averaged across axes and lags 1, 2, 4, 8. It is a diagnostic, not a universal distortion score."},
    "cross_mean_rd": {"label":"Mean |Δ cross-variable PCC|", "column":"mean_absolute_delta", "scale":"log", "cross":True, "description":"Mean absolute change across variable pairs versus bit rate combined over the participating variables."},
    "cross_max_rd": {"label":"Max |Δ cross-variable PCC|", "column":"max_absolute_delta", "scale":"log", "cross":True, "description":"Maximum absolute change across variable pairs versus bit rate combined over the participating variables."},
}


def read_json(path):
    return json.loads(Path(path).read_text())


def rows(path):
    with Path(path).open(newline="",encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def point_key(row):
    return row["dataset"],row["field"],row["codec"],float(row["alpha"])


def write_points(path, points):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=("metric","dataset","codec","alpha","bits_per_value","value","fields","pairs"),lineterminator="\n")
        writer.writeheader();writer.writerows(points)


def collect_points(quality, baseline, audit_path, cross_root):
    qa=read_json(quality/"audit.json");pa=read_json(audit_path)
    if not qa["complete"] or qa["error_count"] or qa["actual_points"] != qa["expected_points"]:
        raise ValueError("quality input is not completely audited")
    if pa["strict_bound_violations"] or pa["max_threads"]!=1 or not pa["input_hashes_rechecked"]:
        raise ValueError("baseline is not an audited single-thread study")
    measured=rows(quality/"points.csv");baseline_rows=rows(baseline)
    q={point_key(r):r for r in measured};p={point_key(r):r for r in baseline_rows}
    if len(q)!=len(measured) or len(p)!=len(baseline_rows) or len(q)!=qa["expected_points"] or set(q)!=set(p):
        raise ValueError("quality and baseline case coverage differ")
    grouped=defaultdict(list);field_hashes={};excluded=set()
    for key,qrow in q.items():
        dataset,field,codec,alpha=key;perf=p[key]
        if qrow["verification"]!="ok":raise ValueError(f"unverified point {key}")
        if qrow["suspected_fill_value"]=="True" or qrow["duplicate_of"]:
            excluded.add((dataset,field));continue
        if not math.isclose(float(qrow["ratio"]),float(perf["ratio"]),rel_tol=1e-10):
            raise ValueError(f"baseline ratio differs from quality result: {key}")
        prior=field_hashes.setdefault((dataset,field),qrow["input_sha256"])
        if prior!=qrow["input_sha256"]:raise ValueError(f"input hash changes: {key}")
        if alpha in ALPHAS:grouped[(dataset,codec,alpha)].append((perf,qrow))
    expected={dataset:sorted(field for ds,field in field_hashes if ds==dataset) for dataset in DATASETS}
    points=[]
    for dataset in DATASETS:
        for codec in CODECS:
            for alpha in ALPHAS:
                pair=grouped[(dataset,codec,alpha)]
                if sorted(x[0]["field"] for x in pair)!=expected[dataset]:raise ValueError(f"incomplete cohort {dataset} {codec} {alpha}")
                bits=8*sum(float(a["mean_compressed_bytes"]) for a,_ in pair)/sum(int(a["elements"]) for a,_ in pair)
                for name,spec in METRICS.items():
                    if spec.get("cross"):continue
                    values=[]
                    for _,r in pair:
                        raw=r[spec["column"]]
                        if not raw:raise ValueError(f"undefined {name} at {dataset} {codec} {alpha}")
                        val=float(raw)
                        if spec.get("transform")=="one_minus":val=1-val
                        if not math.isfinite(val):raise ValueError(f"non-finite {name}")
                        if spec["scale"]=="log" and val<0:raise ValueError(f"negative logarithmic metric {name}")
                        values.append(val)
                    points.append({"metric":name,"dataset":dataset,"codec":codec,"alpha":alpha,
                                   "bits_per_value":bits,"value":statistics.median(values),"fields":len(pair),"pairs":""})
    cross_fields={}
    for dataset in CROSS_DATASETS:
        for codec in CODECS:
            for alpha in ALPHAS:
                label=f"1e-{round(-math.log10(alpha))}"
                path=cross_root/dataset/(codec+"__"+label+".json")
                result=read_json(path)
                fields=sorted(result["fields"])
                prior=cross_fields.setdefault(dataset,fields)
                if fields!=prior or result["dataset"]!=dataset or result["codec"]!=codec or result["alpha"]!=alpha:
                    raise ValueError(f"cross-variable configuration mismatch: {path}")
                if result["valid_pairs"]!=result["total_pairs"] or result["total_pairs"]!=len(fields)*(len(fields)-1)//2:
                    raise ValueError(f"incomplete cross-variable pairs: {path}")
                for field in fields:
                    if result["input_sha256"][field]!=field_hashes[(dataset,field)]:
                        raise ValueError(f"cross-variable source mismatch: {path} {field}")
                selected=[p[(dataset,field,codec,alpha)] for field in fields]
                bits=8*sum(float(r["mean_compressed_bytes"]) for r in selected)/sum(int(r["elements"]) for r in selected)
                for name,spec in METRICS.items():
                    if not spec.get("cross"):continue
                    val=result[spec["column"]]
                    if not isinstance(val,(float,int)) or not math.isfinite(val) or val<0:
                        raise ValueError(f"undefined cross-variable metric: {path}")
                    points.append({"metric":name,"dataset":dataset,"codec":codec,"alpha":alpha,
                                   "bits_per_value":bits,"value":val,"fields":len(fields),"pairs":result["valid_pairs"]})
    return points,expected,cross_fields,sorted(f"{d}/{f}" for d,f in excluded)


def flat_tail_limits(lookup):
    """Find how many points to keep and the rate limit for each focused view."""
    limits = defaultdict(dict)
    point_counts = {}
    for name in SIMILARITY_METRICS:
        for dataset in DATASETS:
            curves = [lookup[name, dataset, codec] for codec in CODECS]
            if any(len(curve) < 2 or curve[-1]["value"] < PLATEAU_SCORE for curve in curves):
                continue
            counts = []
            for curve in curves:
                last_below = max((i for i, point in enumerate(curve) if point["value"] < PLATEAU_SCORE), default=-1)
                # Keep at least two points when a codec starts inside the plateau.
                counts.append(max(2, last_below + 2))
            limit = 1.08 * max(curve[count - 1]["bits_per_value"] for curve, count in zip(curves, counts))
            full_range = max(curve[-1]["bits_per_value"] for curve in curves)
            if 0 < limit < .9 * full_range:
                limits[name][dataset] = limit
                for codec, count in zip(CODECS, counts):
                    point_counts[name, dataset, codec] = count
    return dict(limits), point_counts


def include_unit_score_tick(ax):
    low, high = ax.get_ylim()
    if low < 1 <= high:
        ticks = [tick for tick in ax.get_yticks() if low <= tick <= 1 - .1 * (1 - low)]
        ax.set_yticks([*ticks, 1])


def render_figures(points, output):
    output.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({"font.size":11,"axes.titlesize":13,"axes.spines.top":False,
                         "axes.spines.right":False,"pdf.fonttype":42,"ps.fonttype":42})
    lookup=defaultdict(list)
    for point in points:lookup[(point["metric"],point["dataset"],point["codec"])].append(point)
    for series in lookup.values():
        series.sort(key=lambda point: point["bits_per_value"])
    zoom_limits, focused_counts = flat_tail_limits(lookup)
    legend=[Line2D([],[],color=COLORS[c],marker=MARKERS[c],linestyle=LINES[c],linewidth=1.8,
                   markerfacecolor="white",markeredgewidth=1.1,label="SZ3.3" if c=="SZ3" else c) for c in CODECS]
    figures = []
    full_figures = []

    def draw_curves(ax, name, dataset, *, compact=False, focused=False):
        all_values=[]
        for codec in CODECS:
            series=lookup[name,dataset,codec]
            if len(series)!=len(ALPHAS):raise ValueError(f"incomplete curve {name} {dataset} {codec}")
            if focused:
                series = series[:focused_counts[name, dataset, codec]]
            values=[r["value"] for r in series];all_values.extend(values)
            ax.plot([r["bits_per_value"] for r in series],values,
                    color=COLORS[codec],marker=MARKERS[codec],linestyle=LINES[codec],
                    markerfacecolor="white",markeredgewidth=0.85 if compact else 1.15,
                    markersize=3.6 if compact else 5,linewidth=1.35 if compact else 1.8)
        return all_values

    def ssim_inset(ax, dataset):
        points = [point for codec in CODECS for point in lookup["ssim_rd", dataset, codec]]
        smallest = min(point["value"] for point in points if point["alpha"] <= ALPHAS[-2])
        gap = 1 - smallest
        if not 0 < gap <= .01:
            return

        # Round the window out to include both tightest error bounds for every codec.
        digits = -math.ceil(math.log10(gap))
        bottom = 1 - 10.0**(-digits)
        rates = [point["bits_per_value"] for point in points if point["value"] >= bottom]
        padding = .05 * (max(rates) - min(rates)) or .05
        inset = ax.inset_axes([.42, .13, .54, .42])
        draw_curves(inset, "ssim_rd", dataset, compact=True)
        inset.set_xlim(max(0, min(rates) - padding), max(rates) + padding)
        inset.set_ylim(bottom - .04 * (1 - bottom), 1 + .04 * (1 - bottom))
        ticks = [bottom, (bottom + 1) / 2, 1]
        inset.set_yticks(ticks, [f"{value:.{digits + 1}f}".rstrip("0").rstrip(".") for value in ticks])
        inset.xaxis.set_major_locator(MaxNLocator(nbins=4))
        inset.set_title("SSIM near 1", fontsize=8, pad=4)
        inset.tick_params(axis="both", labelsize=7, length=2.5, pad=2)
        inset.spines[["top", "right"]].set_visible(True)
        inset.grid(alpha=.25, linewidth=.6)

    def panel(ax,name,dataset,*,compact=False,rate_limit=None):
        spec=METRICS[name]
        all_values=draw_curves(ax, name, dataset, compact=compact, focused=rate_limit is not None)
        if spec["scale"]=="log":
            if min(all_values)<0:raise ValueError(f"negative log-axis value: {name} {dataset}")
            positive=[v for v in all_values if v>0]
            if any(v==0 for v in all_values):
                ax.set_yscale("symlog",linthresh=min(positive)/10 if positive else 1e-12)
                if not positive:ax.set_ylim(-1e-12,1e-12)
            else:ax.set_yscale("log")
        else:
            low,high=min(all_values),max(all_values)
            pad=max((high-low)*.06,1e-8);ax.set_ylim(max(-1.02,low-pad),high+pad)
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
            formatter=ScalarFormatter(useOffset=False);ax.yaxis.set_major_formatter(formatter)
        ax.set_xlim(left=0, right=rate_limit)
        ax.set_xlabel("Bit rate (bits/value) · focused range" if rate_limit is not None else "Bit rate (bits/value)")
        ax.set_ylabel(spec["label"])
        ax.set_title(dataset)
        ax.grid(alpha=.25,linewidth=.7);ax.set_axisbelow(True)

    def save(fig,stem,paths):
        fig.savefig(output/(stem+".png"),dpi=180,bbox_inches="tight")
        fig.savefig(output/(stem+".pdf"),bbox_inches="tight")
        plt.close(fig);paths.append(stem)
    for name,spec in METRICS.items():
        datasets=CROSS_DATASETS if spec.get("cross") else DATASETS
        limits = zoom_limits.get(name, {})
        views = [("", limits, figures)]
        if limits:
            views.append(("_full", {}, full_figures))
        for suffix, rate_limits, paths in views:
            fig,axes=panel_row(len(datasets))
            for ax,dataset in zip(axes,datasets):
                panel(ax,name,dataset,compact=True,rate_limit=rate_limits.get(dataset))
                compact_axis(ax,dataset)
                if name in SIMILARITY_METRICS:
                    include_unit_score_tick(ax)
            xlabel = "Bit rate (bits/value) · focused range" if rate_limits else "Bit rate (bits/value)"
            label_row(fig,xlabel,spec["label"])
            fig.legend(handles=legend,loc="upper center",ncol=len(CODECS),frameon=False,
                       fontsize=9,bbox_to_anchor=(.5,.99),columnspacing=1.35)
            save(fig,"datasets_"+name+suffix,paths)
            for dataset in datasets:
                if suffix and dataset not in limits:
                    continue
                fig,ax=plt.subplots(figsize=(6.5,4.8))
                rate_limit = rate_limits.get(dataset)
                panel(ax,name,dataset,rate_limit=rate_limit)
                if name in SIMILARITY_METRICS:
                    include_unit_score_tick(ax)
                    if name=="ssim_rd" and rate_limit is None:
                        ssim_inset(ax, dataset)
                    fig.legend(handles=legend,loc="upper center",ncol=len(CODECS),frameon=False,fontsize=8)
                    fig.tight_layout(rect=(0,0,1,.93))
                else:
                    ax.legend(handles=legend,loc="best",fontsize=8,frameon=True)
                    fig.tight_layout()
                save(fig,dataset+"_"+name+suffix,paths)
    return sorted(figures), sorted(full_figures), zoom_limits


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--quality",type=Path,default=ROOT/"docs/data/quality")
    p.add_argument("--baseline",type=Path,default=ROOT/"docs/data/sdrbench/summary_by_field.csv")
    p.add_argument("--baseline-audit",type=Path,default=ROOT/"docs/data/sdrbench/audit.json")
    p.add_argument("--cross-root",type=Path,required=True,help="verified run's cross/ directory")
    p.add_argument("--output",type=Path,default=ROOT/"docs/data/quality/figures")
    p.add_argument("--results",type=Path,default=ROOT/"docs/data/results.json")
    a=p.parse_args();quality=a.quality.resolve();output=a.output.resolve()
    points,fields,cross_fields,excluded=collect_points(quality,a.baseline,a.baseline_audit,a.cross_root)
    write_points(quality/"quality_rd_points.csv",points)
    figures,full_figures,zoom_limits=render_figures(points,output)
    manifest={"schema_version":1,"bounds":list(ALPHAS),"datasets":list(DATASETS),
      "cross_datasets":list(CROSS_DATASETS),"metrics":METRICS,"figures":figures,
      "full_range_figures":full_figures,"zoomed_bit_rates":zoom_limits,
      "correlation_display":"SSIM and Pearson r use their original scores on linear axes. In the focused view each curve ends at the first point of its sustained 0.999 plateau and keeps at least two points. The rate axis has 8% padding. The focused view is used when it shortens the rate axis by at least 10%. Full-range figures and the CSV show all measured points.",
      "field_counts":{d:len(v) for d,v in fields.items()},"excluded_fields":excluded,
      "cross_fields":cross_fields,"source_audit":"./data/quality/audit.json",
      "quality_points_sha256":hashlib.sha256((quality/"points.csv").read_bytes()).hexdigest(),
      "baseline_summary_sha256":hashlib.sha256(a.baseline.read_bytes()).hexdigest(),
      "aggregation":"Combined bit rate: 8 × sum(mean compressed bytes) / sum(elements); single-field metrics: median over the same fields; cross-variable metrics: mean or max absolute pair change.",
      "cross_note":"Cross-variable bit rates combine only the fields in each audited correlation matrix; index alignment does not establish physical co-location.",
      "ssim_note":"Uniform 7-cell windows per axis, stride 4; valid windows. A singleton leading dimension is analyzed as 2D. SSIM loss is 1−SSIM.",
      "spectral_note":"Full-grid FFT, mean removed, rectangular window and unit grid spacing. Power L1 is not energy loss.",
      "acf_note":"Valid boundaries; lags 1, 2, 4, 8 by axis. Error ACF is diagnostic and has no universal optimization direction."}
    (quality/"rd_manifest.json").write_text(json.dumps(manifest,indent=2,allow_nan=False)+"\n")
    results=read_json(a.results);results["quality_rd"]={"figures":figures,"bounds":list(ALPHAS),"metrics":METRICS,
        "cross_datasets":list(CROSS_DATASETS),"full_range_figures":full_figures,"zoomed_bit_rates":zoom_limits}
    a.results.write_text(json.dumps(results,separators=(",",":"),allow_nan=False)+"\n")
    print(f"Generated {len(figures)} figures ({len(points)} points)")


if __name__=="__main__":main()
