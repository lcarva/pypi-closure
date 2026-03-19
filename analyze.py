"""Analyze PyPI download data to find minimum dependency-complete rebuild sets."""

import ast
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
from packaging.requirements import Requirement

DATA_DIR = Path(__file__).parent / "data"
REPORT_DIR = Path(__file__).parent / "report"

COVERAGE_THRESHOLDS = [0.80, 0.90, 0.95]


def normalize_name(name: str) -> str:
    """PEP 503 normalize a package name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def load_downloads(path: Path) -> pd.DataFrame:
    """Load download counts CSV into a DataFrame."""
    df = pd.read_csv(path)
    df.columns = ["project", "downloads"]
    df["project"] = df["project"].str.strip().apply(normalize_name)
    df = df.groupby("project", as_index=False)["downloads"].sum()
    df = df.sort_values("downloads", ascending=False).reset_index(drop=True)
    return df


def parse_requires_dist(raw: str) -> list[str]:
    """Parse a requires_dist array string into base package names.

    Filters out dependencies that are conditional on extras (e.g.,
    'foo ; extra == "dev"') since those aren't installed by default.
    Keeps deps with environment markers like platform or python_version.
    """
    if not raw or raw == "[]":
        return []

    try:
        items = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return []

    deps = []
    for item in items:
        try:
            req = Requirement(item)
        except Exception:
            continue

        # Skip extras-only dependencies
        if req.marker:
            marker_str = str(req.marker)
            # Skip if the marker requires an extra
            if "extra ==" in marker_str or "extra ==" in marker_str or "extra==" in marker_str:
                continue

        deps.append(normalize_name(req.name))

    return deps


def load_deps(path: Path) -> dict[str, list[str]]:
    """Load dependency CSV into a dict of package -> [dependency names].

    Returns normalized (lowercase) package names.
    """
    deps = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = normalize_name(row["name"].strip())
            # Support both old ("requires_dist") and new ("deps") column names
            raw_deps = row.get("deps") or row.get("requires_dist", "")
            requires = parse_requires_dist(raw_deps)
            deps[name] = requires
    return deps


def build_dependency_graph(deps: dict[str, list[str]]) -> dict[str, set[str]]:
    """Build a directed graph: package -> set of direct dependencies."""
    graph = {}
    for pkg, dep_list in deps.items():
        graph[pkg] = set(dep_list)
    return graph


def transitive_closure(graph: dict[str, set[str]], packages: set[str]) -> set[str]:
    """Compute the transitive closure of a set of packages.

    Returns all packages needed (including the input set) to satisfy
    the full dependency tree.
    """
    needed = set()
    stack = list(packages)

    while stack:
        pkg = stack.pop()
        if pkg in needed:
            continue
        needed.add(pkg)
        for dep in graph.get(pkg, set()):
            if dep not in needed:
                stack.append(dep)

    return needed


def compute_coverage_sets(
    downloads: pd.DataFrame,
    graph: dict[str, set[str]],
    thresholds: list[float],
) -> list[dict]:
    """For each coverage threshold, find the minimum set of top packages
    whose transitive closure covers that % of total downloads.

    Returns a list of dicts with analysis results.
    """
    total_downloads = downloads["downloads"].sum()
    results = []

    for threshold in thresholds:
        target = total_downloads * threshold
        cumulative = 0
        top_packages = set()

        for _, row in downloads.iterrows():
            top_packages.add(row["project"])
            cumulative += row["downloads"]
            if cumulative >= target:
                break

        closure = transitive_closure(graph, top_packages)
        transitive_deps = closure - top_packages

        # Downloads covered by the closure (including transitive deps)
        closure_downloads = downloads[downloads["project"].isin(closure)]["downloads"].sum()

        results.append({
            "threshold": threshold,
            "top_packages_count": len(top_packages),
            "transitive_deps_count": len(transitive_deps),
            "total_closure_size": len(closure),
            "top_packages_downloads": cumulative,
            "closure_downloads": closure_downloads,
            "closure_coverage": closure_downloads / total_downloads,
            "total_downloads": total_downloads,
            "top_packages": sorted(top_packages),
            "transitive_deps": sorted(transitive_deps),
        })

    return results


def generate_report(results: list[dict], downloads: pd.DataFrame, output_path: Path):
    """Write analysis results to a markdown report."""
    total = results[0]["total_downloads"]

    lines = [
        "# PyPI Minimum Rebuild Set Analysis",
        "",
        f"**Total downloads (Linux + cp312 and pure-Python, last 30 days):** {total:,.0f}",
        f"**Total packages with downloads:** {len(downloads):,}",
        "",
        "## Coverage Summary",
        "",
        "| Target | Top Packages | + Transitive Deps | = Total Set | Actual Coverage |",
        "|--------|-------------|-------------------|-------------|-----------------|",
    ]

    for r in results:
        lines.append(
            f"| {r['threshold']:.0%} | {r['top_packages_count']:,} "
            f"| +{r['transitive_deps_count']:,} "
            f"| {r['total_closure_size']:,} "
            f"| {r['closure_coverage']:.1%} |"
        )

    lines.extend(["", "## Top 20 Packages by Downloads", ""])
    lines.append("| Rank | Package | Downloads | Cumulative % |")
    lines.append("|------|---------|-----------|-------------|")

    cumulative = 0
    for i, (_, row) in enumerate(downloads.head(20).iterrows(), 1):
        cumulative += row["downloads"]
        pct = cumulative / total * 100
        lines.append(f"| {i} | {row['project']} | {row['downloads']:,.0f} | {pct:.1f}% |")

    for r in results:
        lines.extend([
            "",
            f"## {r['threshold']:.0%} Coverage Detail",
            "",
            f"- **Top packages (by downloads):** {r['top_packages_count']:,}",
            f"- **Additional transitive dependencies:** {r['transitive_deps_count']:,}",
            f"- **Total packages to rebuild:** {r['total_closure_size']:,}",
            f"- **Actual download coverage:** {r['closure_coverage']:.1%}",
        ])

        if r["transitive_deps"]:
            lines.extend([
                "",
                "<details>",
                "<summary>Transitive dependencies not in top set (click to expand)</summary>",
                "",
            ])
            for dep in r["transitive_deps"]:
                lines.append(f"- {dep}")
            lines.extend(["", "</details>"])

    lines.append("")
    output_path.write_text("\n".join(lines))
    print(f"Report written to {output_path}")


def generate_package_lists(results: list[dict], output_dir: Path):
    """Write a text file per threshold with the full package closure, one per line."""
    for r in results:
        pct = int(r["threshold"] * 100)
        all_packages = sorted(set(r["top_packages"]) | set(r["transitive_deps"]))
        path = output_dir / f"{pct}_coverage.txt"
        path.write_text("\n".join(all_packages) + "\n")
        print(f"  Package list written to {path}")


def main():
    downloads_path = DATA_DIR / "downloads.csv"
    deps_path = DATA_DIR / "deps.csv"

    if not downloads_path.exists() or not deps_path.exists():
        print("Data files not found. Run fetch_data.py first.")
        sys.exit(1)

    print("Loading data...")
    downloads = load_downloads(downloads_path)
    deps = load_deps(deps_path)

    print(f"  {len(downloads)} packages with download data")
    print(f"  {len(deps)} packages with dependency metadata")

    print("Building dependency graph...")
    graph = build_dependency_graph(deps)

    print("Computing coverage sets...")
    results = compute_coverage_sets(downloads, graph, COVERAGE_THRESHOLDS)

    for r in results:
        print(
            f"  {r['threshold']:.0%}: {r['top_packages_count']} top + "
            f"{r['transitive_deps_count']} transitive = "
            f"{r['total_closure_size']} total ({r['closure_coverage']:.1%} actual coverage)"
        )

    REPORT_DIR.mkdir(exist_ok=True)
    generate_report(results, downloads, REPORT_DIR / "results.md")
    generate_package_lists(results, REPORT_DIR)


if __name__ == "__main__":
    main()
