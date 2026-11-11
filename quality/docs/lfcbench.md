# Registering LFCQuality with LFCBenchmark

LFCQuality is independent of the benchmark runner. Its Python API and CLI work
without importing or installing lfcbench.

## Automatic installed-plugin discovery

openSDC-Bench already provides `lfcbench.register_metric`,
`lfcbenchmark.metrics` discovery, `quality_metrics` in YAML/Python, and
`lfcbench list-metrics`. Install both components from the benchmark repository
root; no separate quality checkout or integration patch is needed:

```bash
python -m pip install -e . -e ./quality
lfcquality build --openmp required --fftw required
lfcbench list-metrics
```

The discovered name is `lfcquality`. Its entry point is
`lfcquality.integration:quality_metric`, which accepts
`(original, reconstructed, **options)` and returns a JSON-compatible dictionary.

```python
import numpy as np
from lfcbench import AbsoluteError, benchmark

data = np.arange(16**3, dtype=np.float32).reshape(16, 16, 16)
record = benchmark(
    data, compressor="identity", error=AbsoluteError(1e-3),
    quality_metrics=[{
        "name": "lfcquality",
        "options": {"metrics": ["psnr", "pcc", "ssim", "autocorrelation"],
                    "threads": 4, "ssim_stride": 4},
    }],
)
print(record["metrics"]["quality"]["lfcquality"])
```

Equivalent additional YAML section:

```yaml
quality_metrics:
  - name: lfcquality
    options:
      threads: 8
      fft_threads: 4
      metrics: [psnr, ssim, pcc, error_autocorrelation, autocorrelation, spectral]
```

This is optional. Existing benchmark configurations run the original independent
bound verification and timing protocol without extra metric work.

## Explicit registration

For a Python session or an lfcbench `--plugin` module:

```python
from lfcquality.integration import register_with_lfcbench
register_with_lfcbench("my_lab.quality")
```

Then use `name: my_lab.quality`. Direct registration is equally valid:

```python
from lfcbench import register_metric
from lfcquality import analyze
register_metric("my_lab.quality", analyze)
```

Use one source of registration per name. The installed `lfcquality` entry point
already owns that name; direct registration under it would create a deliberate
collision error.

## Timing and field groups

Metric plugins run after the compression and decompression timers stop, and
only on measured trials, not warmups. Inputs are read-only views. The metric
does not alter compressor options, CPU affinity or global OpenMP thread counts.
The result's `analysis_seconds` is distinct from codec throughput.

Even untimed analysis consumes machine resources and changes cache/thermal
state. For a strict timing study, analyze saved reconstructions in a separate
phase. If interleaving analysis and codec calls, consider
`OMP_WAIT_POLICY=PASSIVE` before process startup, and document the protocol.
The adapter does not automatically dump reconstructed files or rerun existing
benchmark measurements. Existing scalar summary JSON cannot recover these
correlation or spectral metrics.

A per-trial plugin receives one original/reconstructed pair, so its output
contains the six single-field metric groups. Cross-variable changes require
the separate `analyze_fields` API or `compare-fields` command with aligned
variables from the same codec/configuration/error case. The program does not
pair unrelated trials or infer alignment from filenames.
