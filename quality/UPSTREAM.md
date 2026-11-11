# LFCQuality in openSDC-Bench

This directory contains the LFCQuality C++, C, and Python source as a regular
part of openSDC-Bench. It was imported from
[BingluCS/LFCQuality](https://github.com/BingluCS/LFCQuality) at commit
`6f611e8c8b2677eec09e939e5c3ce6eb9e9e4c01` with its original BSD-3-Clause
license in [LICENSE](LICENSE). It is not a Git submodule; contributors can
propose changes directly in this repository.

Install the optional Python package with `python -m pip install -e ./quality`.
See [README.md](README.md) for the native C/C++ and Python interfaces,
OpenMP/FFTW build options, supported metrics, and tests. Quality analysis runs
outside compression/decompression timing in the benchmark integration.
