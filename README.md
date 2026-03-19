# PyPI Minimum Rebuild Set Analysis

Determines the smallest set of PyPI packages that constitutes a meaningful,
dependency-complete offering for a controlled wheel-rebuilding environment.

## Why not just take the top N packages?

Taking the most-downloaded packages by popularity alone doesn't work because
**dependency completeness matters**. If users can only install packages you've
rebuilt, every transitive dependency must also be in your set — otherwise
installs will fail at dependency resolution time.

For example, the top 139 most-downloaded packages (Linux, cp312) cover ~80% of
real-world installs, but they pull in 141 *additional* transitive dependencies
that aren't in that top-139 list. Without those, popular packages like
`cryptography`, `pydantic`, and `google-auth` would be uninstallable.

This project computes the **transitive closure** — for any target coverage
threshold, it finds the top packages *plus* every package their dependency
trees require — giving you the true minimum rebuild set.

## Results (sample run)

| Target | Top Packages | + Transitive Deps | Total to Rebuild |
|--------|-------------|-------------------|-----------------|
| 80%    | 139         | +141              | 280             |
| 90%    | 290         | +318              | 608             |
| 95%    | 535         | +470              | 1,005           |

## Data source

Download statistics and dependency metadata come from
[ClickPy](https://clickpy.clickhouse.com/), a free public ClickHouse database
of PyPI download logs. No BigQuery billing account is required.

**Note:** The fetched `data/downloads.csv` will contain ~39,000 packages, far
fewer than the hundreds of thousands listed on PyPI. This is expected — the
query only returns packages with at least one download in the selected time
window (Linux, Python 3.12, last 30 days). The majority of PyPI packages are
abandoned, empty, or test uploads with zero recent downloads and are excluded.

## Usage

```
make run    # fetch data from ClickPy, then run analysis (sets up venv automatically)
make fetch  # fetch data only
make analyze  # run analysis only
make test   # run tests
make clean  # remove venv and generated files
```

`make run` does everything end-to-end: creates a virtualenv, installs
dependencies, fetches data, and runs the analysis.

**Outputs:**
- `data/downloads.csv`, `data/deps.csv` — raw data from ClickPy
- `report/results.md` — human-readable report
- `report/80_coverage.txt`, `report/90_coverage.txt`, `report/95_coverage.txt` — machine-readable package lists (one package per line) containing the full closure for each threshold
