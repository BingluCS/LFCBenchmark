# Contributing to openSDC-Bench

Fork [openSDC-Bench](https://github.com/opensdc-org/OpenSDC-Bench), create a
branch, and open a pull request. Improvements to compressor adapters, C/C++
quality metrics, data descriptions, validation, documentation, and tests are
welcome. The public website has its own
[source repository](https://github.com/opensdc-org/benchmark).

## Repository map

| Directory | Purpose |
| --- | --- |
| `src/lfcbench/` | Python benchmark API, CLI, compressor and metric registries |
| `native/`, `native_typed/` | C++ single-thread benchmark drivers |
| `quality/` | LFCQuality C/C++, Python, tests and license |
| `third_party/` | Pinned upstream compressor submodules |
| `datasets/` | Data sources, field descriptions and access guide |
| `scripts/` | Builds, execution, audit, plotting and website-data export |
| `docs/data/` | Published measurements, quality summaries, audits and figures |
| `docs/` | Project documentation and published results |
| `tests/`, `examples/` | Automated checks and extension examples |

## Local development

```bash
git clone --recurse-submodules https://github.com/opensdc-org/OpenSDC-Bench.git
cd OpenSDC-Bench
python -m pip install -e '.[test]'
python -m pip install -e './quality[test]'
lfcquality build --openmp required --fftw required
python -m pytest -q
```

The quality component needs a C++17 compiler, OpenMP and FFTW development
libraries. See [`quality/README.md`](quality/README.md) for C/C++ builds and
other options. Compressor registration and metric extension are documented in
[`docs/leaderboard.md`](docs/leaderboard.md), with examples in `examples/`.
The Python plugin path and native C++ timing path are separate; registering a
Python compressor does not automatically add a native timing result.

## Adding or changing results

The public comparison uses the field selection, error semantics, timing scope,
machine, thread count and quality options documented with each cohort. Run
the relevant benchmark and quality analysis, retain raw measurements and
independent audits, and submit the source revision, data details, hardware and
complete cohort evidence. Missing fields, mismatched quality/size information,
and invalid error bounds are rejected by the export checks.

Automated checks verify consistency and build the leaderboard from the
repository's audited inputs. They do **not** independently reproduce timings
or authenticate a contributor's machine: maintainers must review evidence and
run or verify measurements on comparable hardware before publishing them.
Do not compare GitHub Actions runner timings with the public single-thread
cohort. Particle data, halo/subhalo workflows, and domain-specific task
evaluation remain future work.

After reviewed inputs are merged into the benchmark repository, the website
build regenerates the leaderboard and publishes it. See
[`docs/publication.md`](docs/publication.md) for the exact inputs and commands.
