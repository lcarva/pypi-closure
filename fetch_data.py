"""Fetch PyPI download counts and dependency metadata from ClickPy (ClickHouse)."""

import csv
import io
import sys
from pathlib import Path

import requests

CLICKHOUSE_URL = "https://sql-clickhouse.clickhouse.com/"
CLICKHOUSE_PARAMS = {"user": "demo"}
DATA_DIR = Path(__file__).parent / "data"

# Downloads: packages on Linux + Python 3.12, plus pure-Python (universal) wheels,
# in the last 30 days.
DOWNLOADS_QUERY = """\
SELECT project, count() AS downloads
FROM pypi.pypi
WHERE date >= today() - 30
  AND (
    (system = 'Linux' AND python_minor = '3.12')
    OR (system = '' AND python_minor = '')
  )
GROUP BY project
ORDER BY downloads DESC
FORMAT CSVWithNames
"""

# Dependencies: latest version's requires_dist for a batch of packages.
# Uses argMax to pick the most recently uploaded version, filtered to only
# rows that actually have requires_dist populated.
DEPS_QUERY_TEMPLATE = """\
SELECT
    name,
    argMax(version, upload_time) AS latest_version,
    argMax(requires_dist, upload_time) AS deps
FROM pypi.projects
WHERE name IN ({placeholders})
AND length(requires_dist) > 0
GROUP BY name
FORMAT CSVWithNames
"""

DEPS_BATCH_SIZE = 500


def query_clickhouse(sql: str, timeout: int = 600) -> str:
    """Execute a SQL query against the ClickPy ClickHouse endpoint.

    Returns the raw response text (CSV).
    """
    resp = requests.post(
        CLICKHOUSE_URL,
        params=CLICKHOUSE_PARAMS,
        data=sql.encode("utf-8"),
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.text


def fetch_downloads(output_path: Path) -> list[str]:
    """Fetch download counts and write to CSV. Returns list of package names."""
    print("Fetching download counts (Linux + cp312 and pure-Python, last 30 days)...")
    text = query_clickhouse(DOWNLOADS_QUERY)
    output_path.write_text(text)

    # Parse out package names for the deps step
    reader = csv.DictReader(io.StringIO(text))
    packages = [row["project"] for row in reader]
    print(f"  -> {len(packages)} packages written to {output_path}")
    return packages


def fetch_deps(packages: list[str], output_path: Path) -> int:
    """Fetch dependency metadata in batches and write to CSV. Returns row count."""
    print(f"Fetching dependency metadata for {len(packages)} packages in batches of {DEPS_BATCH_SIZE}...")

    all_rows = []
    header = None

    for i in range(0, len(packages), DEPS_BATCH_SIZE):
        batch = packages[i : i + DEPS_BATCH_SIZE]
        placeholders = ", ".join(f"'{pkg.replace(chr(39), chr(39)*2)}'" for pkg in batch)
        query = DEPS_QUERY_TEMPLATE.format(placeholders=placeholders)

        batch_num = i // DEPS_BATCH_SIZE + 1
        total_batches = (len(packages) + DEPS_BATCH_SIZE - 1) // DEPS_BATCH_SIZE
        print(f"  batch {batch_num}/{total_batches} ({len(batch)} packages)...")

        text = query_clickhouse(query)
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)

        if not rows:
            continue

        if header is None:
            header = rows[0]
            all_rows.extend(rows[1:])
        else:
            all_rows.extend(rows[1:])  # skip header on subsequent batches

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(all_rows)

    print(f"  -> {len(all_rows)} packages with dependencies written to {output_path}")
    return len(all_rows)


def main():
    DATA_DIR.mkdir(exist_ok=True)

    downloads_path = DATA_DIR / "downloads.csv"
    deps_path = DATA_DIR / "deps.csv"

    packages = fetch_downloads(downloads_path)
    fetch_deps(packages, deps_path)

    print("\nDone. Data saved to:")
    print(f"  {downloads_path}")
    print(f"  {deps_path}")


if __name__ == "__main__":
    main()
