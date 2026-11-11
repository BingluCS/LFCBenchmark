# Scientific datasets

The benchmark uses public scientific data; large binary arrays are **not**
stored in this Git repository. The table lists the five datasets for which a
download source and an exact field manifest are currently published here.
Follow the data provider's terms and citation instructions.

| Dataset | Published fields | Layout used here | Original data source |
| --- | ---: | --- | --- |
| NYX | 6 | `float32`, 512 × 512 × 512 | [SDRBench NYX](https://huggingface.co/datasets/sdrbench/nyx) |
| CESM-ATM | 77 | `float32`, 1800 × 3600 | [SDRBench CESM-ATM, raw 2D](https://huggingface.co/datasets/sdrbench/cesm-atm) |
| Hurricane Isabel | 20 | `float32`, 100 × 500 × 500 | [SDRBench Hurricane, snapshot 48](https://huggingface.co/datasets/sdrbench/hurricane-isabel) |
| Miranda | 7 | original `float64`, 256 × 384 × 384 | [SDRBench Miranda, small](https://huggingface.co/datasets/sdrbench/miranda) |
| SCALE-LETKF | 12 | `float32`, 98 × 1200 × 1200 | [SDRBench SCALE-LETKF](https://huggingface.co/datasets/sdrbench/scale-letkf) |

All arrays use little-endian values and C-order dimensions. Hurricane includes
13 raw and 7 supplied log10 fields. The two constant CESM fields are excluded
from range-relative evaluation. The benchmark's historical JHTDB results stay
in the existing result tables, but distributing that snapshot is deferred.

## Obtain the reference fields

The [SDRBench dataset catalogue](https://sdrbench.github.io/datasets.html)
links to the provider's archives and mirrors. Download the desired variant,
then arrange the fields under a root directory such as:

```text
data/sdrbench/
  NYX/baryon_density.f32
  NYX/dark_matter_density.f32
  Miranda/density.d64
  CESM/CLDHGH_1_1800_3600.f32
  Hurricane/Pf48.bin.f32
  SCALE/T-98x1200x1200.f32
```

[`sdrbench-fields.json`](sdrbench-fields.json) records each selected file's
relative path, size, data type and shape used in the study. The
archive or mirror may use an additional parent directory: copy or link the
listed files to the layout above, without converting their contents. Full data
access, scientific licenses, and citation terms remain with the upstream
providers.

## Run a dataset

With the official compressor submodules built as described in the
[project README](../README.md), create an inventory and run only the dataset
you downloaded:

```bash
lfcbench native-inventory --data-root data/sdrbench --datasets NYX \
  --output results/nyx-inventory.json
lfcbench native-suite --inventory results/nyx-inventory.json \
  --output results/nyx-run --datasets NYX --cpu 2
lfcbench native-suite-audit results/nyx-run --check-inputs
lfcbench native-suite-plot results/nyx-run --output results/nyx-plots
```

Choose a CPU allowed on your machine. Timing values from different systems or
protocols must not be merged into the same comparison cohort.
