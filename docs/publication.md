# Result validation and publication

The benchmark repository is the source of the measured data and audit inputs;
the separate [website repository](https://github.com/opensdc-org/benchmark)
owns the website presentation and GitHub Pages deployment.

The existing public leaderboard can be rebuilt without the original server:

```bash
python scripts/export_leaderboard.py --output /tmp/opensdc-leaderboard.json
python scripts/build_site_data.py --output /tmp/opensdc-site-data
```

The exporter reads `docs/data/sdrbench/summary_by_field.csv`, the corresponding
performance audit and backend revisions, and the checked-in
`docs/data/quality/{config.json,audit.json,points.csv}`. It verifies matching
field coverage, compressed sizes, normalized errors, and audit
status before producing cohort entries. A codec may be added for a subset of
dataset/error-bound combinations, but every included combination must cover
all eligible fields. Add its pinned source to `docs/data/results.json` and its
name to the quality config. The website displays separate rankings per cohort.

The site-data build copies the published figures and summaries, then rebuilds
`leaderboard.json`; it refuses to overwrite an existing output directory.
The website repository's deployment workflow reads the benchmark's `main`
branch on push, manual invocation, and a regular schedule. This means merged
audited data flow to the website without committing generated website data or
requiring a cross-repository write token.

**Scope of the checks:** JSON/CSV consistency and reported audits do not prove
that external measurements were actually taken as claimed. Changes to results
require maintainer review and, where appropriate, reproduction on the stated
hardware. The existing benchmark measures native calls; custom Python plugin
timings are a separate path. Do not mix them in one timing cohort.

The published quality summaries cover the current reference run. To generate
new quality observations for a changed compressor, reconstruct the original
fields and analyze them with the [quality component](../quality/); they cannot
be derived from compressed sizes alone. The quality-RD figure generator is
currently scoped to the published reference algorithms and needs corresponding
updates when its curve coverage changes.
