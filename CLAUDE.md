# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PyPI Minimum Rebuild Set Analysis — determines the smallest dependency-complete set of PyPI packages for a controlled wheel-rebuilding environment. Computes transitive closures at coverage thresholds (80/90/95%) over download data from ClickPy (public ClickHouse instance of PyPI logs).

## Commands

```bash
make run       # fetch data + run analysis (sets up venv automatically)
make fetch     # fetch data only
make analyze   # run analysis only
make test      # run tests
make clean     # remove venv and generated files
```

## Architecture

Two top-level scripts with no shared module — flat layout, no `src/` directory:

- **`fetch_data.py`** — Queries ClickPy ClickHouse for download counts (Linux+cp312 and pure-Python, last 30 days) and dependency metadata (latest version's `requires_dist`). Fetches deps in batches of 500. Key exports: `query_clickhouse()`, `fetch_downloads()`, `fetch_deps()`, `CLICKHOUSE_URL`.

- **`analyze.py`** — Loads CSVs, builds a dependency graph, computes transitive closure at each coverage threshold. Uses PEP 503 name normalization and PEP 508 marker evaluation (filtering to Linux/x86_64/cp3.12). Outputs a markdown report and per-threshold package list files.

Data flows: `fetch_data.py` -> `data/*.csv` -> `analyze.py` -> `report/results.md` + `report/*_coverage.txt`

## Testing

Tests use the `responses` library to mock HTTP calls to ClickHouse. Tests import directly from `fetch_data` (not a package), so `PYTHONPATH=.` is required.

## Dependencies

Runtime: `requests`, `packaging`, `pandas`. Test: `pytest`, `responses`. Python >= 3.12.
