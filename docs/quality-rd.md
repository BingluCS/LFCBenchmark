# Rate–quality figures

The website's View menu includes PSNR, SSIM, Pearson correlation (PCC),
range-normalized RMSE, relative spectral power L1 and L2, relative Fourier L2,
field autocorrelation change, error autocorrelation, and mean and maximum
cross-variable correlation change.
The measurements cover the five tested error bounds from `1E-1` through `1E-5`.
The quality point CSV and a machine-readable protocol are available from the
website's Downloads section; each displayed image also links to its PDF.

SSIM and Pearson r plots show the original median scores on linear axes.
In the focused view, each curve ends at the first point of its sustained
0.999 plateau and shows at least two points. The rate axis extends 8% past
the longest displayed curve. This view is used when it shortens the rate
axis by at least 10%.
**Full rate range** opens the complete figure, and the CSV includes every point.

Each dataset-level single-field point uses the median of the field metrics. Its
horizontal coordinate is `8 * sum(mean_compressed_bytes) / sum(elements)` over
exactly the same fields. A curve therefore summarizes a multi-field cohort; it
does not represent an individual field's rate–distortion trajectory. CESM's
13 sensitivity exclusions match the leaderboard (12 suspected fill-value
fields and one duplicate). The older performance figures and results table
retain their original measured inputs, including those fields.

Cross-variable curves currently use the audited NYX, Hurricane and Miranda
variable groups only. Their bit rate uses the combined compressed size and
element count of that group's participating fields. Their vertical coordinate
is the mean or maximum absolute change of Pearson correlation across variable
pairs. Shared array indices do not by themselves establish physical
co-location; scientific interpretation requires domain-specific confirmation.

SSIM uses uniform 7-cell windows per axis with stride 4 and valid boundaries.
A singleton leading dimension is analyzed as 2D. The ACF summaries average
lags 1, 2, 4 and 8 over spatial axes with valid boundaries.
Error ACF measures structure in the error and is a diagnostic, without a
universal better-or-worse direction. Spectral metrics use the full FFT grid,
mean removal, a rectangular window and unit spacing. Spectral power L1 is not
the fraction of energy lost; by Parseval's identity Fourier L2 is related to
spatial L2. See `docs/data/quality/rd_manifest.json` for full protocol metadata.

Recreate the plots on HPDPS-8 after the audited result bundle is available:

```bash
conda activate py3.13
cd /data0/lb/lfcbenchmark
python scripts/plot_quality_rd.py \
  --cross-root /data0/lb/lfcbenchmark/results/quality-correlation-full-20261109/cross
```

The script checks the input audits, field and codec coverage, matching
compression ratios and source hashes before producing PNG/PDF files and the
public CSV and manifest. Running `scripts/export_web_results.py` afterward
preserves the quality figures only if the performance and quality source CSVs
still match the hashes in that manifest.
