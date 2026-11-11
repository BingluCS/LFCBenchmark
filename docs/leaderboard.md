# Registration and leaderboard

openSDC-Bench supports three **non-exclusive category labels**: `general`,
`domain_specific` and `particle`. A future cosmology-specific particle
compressor may belong to both `domain_specific` and `particle`. Data-model
and domain tags are separate from categories. Tags describe a plugin; they do
not certify its scientific validity or automatically add a public ranking.

The execution API currently supports finite floating-point grid arrays. The
`particle` label and the empty leaderboard track reserve space for future work;
they do **not** implement a particle data model or particle compressor adapter.
Likewise, halo/subhalo finders and metrics are not implemented at this stage.

## Register a compressor

Existing `register_compressor(name, factory)` and the `Compressor` API remain
compatible. Add metadata to a local registration:

```python
from lfcbench import register_compressor
from my_package import MyCompressor

register_compressor(
    "my_lab.compressor", MyCompressor,
    tracks=("domain_specific",), data_models=("grid",),
    domains=("cosmology",), description="My cosmology adapter",
)
```

The registration can also be used as a decorator. For an independently
installed package, annotate the exported factory with `@plugin_metadata(...)`
and declare it as a Python entry point in `pyproject.toml`:

```toml
[project.entry-points."lfcbenchmark.compressors"]
"my_lab.compressor" = "my_package:MyCompressor"
```

Run `lfcbench --plugin my_package list --track domain_specific` for local
registration, `lfcbench list --track particle --json` to inspect that category,
and `lfcbench inspect my_lab.compressor` for capabilities and metadata. Local
and installed registrations with the same name are rejected. Entry-point
discovery reads package metadata; listing or selecting a plugin may load its
code. `unregister_compressor(name)` removes a local registration without
removing installed entry points or built-ins. Plugins are executable code and
must be trusted. Results record the selected compressor's registration metadata.

## Register domain-specific metrics

Existing `register_metric(name)` functions still work. A metric for the grid
API may declare its domain and request an explicit context:

```python
from lfcbench import register_metric

@register_metric("my_lab.cosmo_quality", tracks=("domain_specific",),
                 data_models=("grid",), domains=("cosmology",),
                 needs_context=True)
def cosmo_quality(original, reconstructed, *, context, **options):
    # Implement the domain analysis using the recorded units/settings.
    return {"my_error": float(abs(original - reconstructed).max())}
```

Pass `metric_context={"domain": "cosmology", ...}` to `benchmark(...)`. A YAML
dataset can also provide `domain` and a JSON-compatible `metadata` mapping;
these become the metric context along with the dataset name and data model.
Metrics run after codec timers and receive read-only array views. Installed
metric packages use the entry-point group `lfcbenchmark.metrics` and can attach
metadata using `@plugin_metadata(...)`. Missing required context and mismatched
domain/data models fail explicitly. `unregister_metric(name)` removes a local
metric registration.

Particle, halo finder and subhalo workflows require additional contracts for
particle IDs, coordinates, simulation units, finder versions, catalog matching
and physical validation. These are future work; no placeholder results are
displayed as measured data. In particular, the SDRBench NYX grid fields used
here are not a particle catalog.

## Ranking and publication policy

There is no single universal compression score. A cohort fixes dataset and
field hashes, track/data model, error mode and bound, processor, thread count,
preprocessing and metric options. Rank on one selected metric with an explicit
`higher` or `lower` direction. `RankingMetric`, `register_ranking_metric` and
`rank_entries` expose this for custom workflows; installed score definitions
use `lfcbenchmark.ranking_metrics`. Missing or unverified values are unranked,
and `rank_entries` rejects records with mixed cohort IDs. Use
`lfcbench list-ranking-metrics` to inspect the registered score directions.

```python
from lfcbench import RankingMetric, register_ranking_metric, rank_entries

register_ranking_metric(RankingMetric("my_error", "My domain error", "lower"))
# Construct these records from audited results in the SAME comparison cohort.
rows = [
    {"cohort": "my-audited-cohort", "codec": "codec-a", "status": "verified",
     "metrics": {"my_error": 0.03}},
    {"cohort": "my-audited-cohort", "codec": "codec-b", "status": "verified",
     "metrics": {"my_error": 0.02}},
]
ranking = rank_entries(rows, metric="my_error", cohort="my-audited-cohort")
```

The values above are illustrative and are not published benchmark results.
See `examples/domain_metric.py` for a runnable grid-metric registration with a
matching ranking direction; it is an interface example, not a validated
climate-science metric.

The website is a static GitHub Pages publication. Plugin installation or local
registration does **not** automatically submit a result or certify it. New
cohorts require an auditable result bundle, explicit metric definition and
maintainer review before publication. Domain-specific and particle rankings
remain empty until comparable, validated results have been added.

The leaderboard's **Link to this ranking** preserves the selected track,
dataset, error bound and ranking metric. **Explore figures** opens the same
dataset and bound in the figure explorer, where **Link to this view** records
the figure and table selection. The table's bound selector changes the table;
the plotted curve retains its documented range of measured bounds.

The current public leaderboard is generated by `scripts/export_leaderboard.py`
from audited SDRBench performance records and verified LFCQuality results.
The exporter requires complete matching field coverage, matching sizes and
normalized errors, and checks both audits. It excludes 12 CESM fields with
suspected `1E36` missing values and the byte-identical `SOLIN` duplicate; the
original archived charts retain their raw inputs. The exact source attributes
of those suspected missing values are still unverified. Cohort identifiers
include the field hashes and metric settings. Ratio is total raw bytes divided
by compressed bytes; throughput is total bytes divided by summed mean field
times and reported in MiB/s (1 MiB = 1,048,576 bytes); PSNR uses element-weighted RMS NRMSE; SSIM, PCC, spectral and field ACF
errors are per-field medians. Full-grid spectral power L1 is an error measure,
not the fraction of energy lost. Compression and quality measurements are
separate and use the same verified reconstruction configuration.
Current throughput fields are named `compress_MiB_s` and `decompress_MiB_s`.
The older `compress_MB_s` and `decompress_MB_s` ranking metrics remain
available for existing records in decimal MB/s; old share links select the
equivalent MiB/s ranking.

```bash
python scripts/export_leaderboard.py --quality /data0/lb/lfcbenchmark/results/quality-correlation-full-20261109
```

TOP500's [published protocol](https://www.top500.org/project/linpack/) uses a
specified benchmark and ranking metric; openSDC-Bench keeps multiple distinct
metrics because compression quality and speed are not interchangeable.
