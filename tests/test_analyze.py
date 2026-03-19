"""Tests for analyze.py."""

from pathlib import Path

import pandas as pd

from analyze import (
    build_dependency_graph,
    compute_coverage_sets,
    generate_report,
    load_deps,
    load_downloads,
    parse_requires_dist,
    transitive_closure,
)


class TestParseRequiresDist:
    def test_simple_deps(self):
        raw = "['urllib3>=1.21.1', 'certifi>=2017.4.17']"
        assert parse_requires_dist(raw) == ["urllib3", "certifi"]

    def test_extras_filtered_out(self):
        raw = "['requests', 'sphinx ; extra == \"docs\"', 'pytest ; extra == \"test\"']"
        result = parse_requires_dist(raw)
        assert result == ["requests"]

    def test_platform_markers_kept(self):
        raw = "['pywin32 ; sys_platform == \"win32\"', 'uvloop ; sys_platform != \"win32\"']"
        result = parse_requires_dist(raw)
        assert "pywin32" in result
        assert "uvloop" in result

    def test_empty(self):
        assert parse_requires_dist("") == []
        assert parse_requires_dist("[]") == []
        assert parse_requires_dist(None) == []

    def test_malformed(self):
        assert parse_requires_dist("not a list") == []

    def test_version_specifiers_stripped(self):
        raw = "['requests>=2.20,<3.0', 'urllib3!=1.25.0,>=1.21.1']"
        result = parse_requires_dist(raw)
        assert result == ["requests", "urllib3"]

    def test_normalized_to_lowercase(self):
        raw = "['PyYAML>=5.0', 'MarkupSafe']"
        result = parse_requires_dist(raw)
        assert result == ["pyyaml", "markupsafe"]


class TestLoadDownloads:
    def test_basic(self, tmp_path):
        csv_content = '"project","downloads"\n"boto3",1000\n"requests",900\n'
        path = tmp_path / "downloads.csv"
        path.write_text(csv_content)
        df = load_downloads(path)
        assert len(df) == 2
        assert df.iloc[0]["project"] == "boto3"
        assert df.iloc[0]["downloads"] == 1000

    def test_normalizes_names(self, tmp_path):
        csv_content = '"project","downloads"\n"PyYAML",500\n'
        path = tmp_path / "downloads.csv"
        path.write_text(csv_content)
        df = load_downloads(path)
        assert df.iloc[0]["project"] == "pyyaml"


class TestLoadDeps:
    def test_basic(self, tmp_path):
        csv_content = (
            '"name","version","requires_dist"\n'
            '"requests","2.31.0","[\'urllib3>=1.21\', \'certifi\']"\n'
        )
        path = tmp_path / "deps.csv"
        path.write_text(csv_content)
        deps = load_deps(path)
        assert "requests" in deps
        assert "urllib3" in deps["requests"]
        assert "certifi" in deps["requests"]


class TestDependencyGraph:
    def test_build_graph(self):
        deps = {
            "a": ["b", "c"],
            "b": ["c"],
            "c": [],
        }
        graph = build_dependency_graph(deps)
        assert graph["a"] == {"b", "c"}
        assert graph["b"] == {"c"}
        assert graph["c"] == set()

    def test_transitive_closure_simple(self):
        graph = {
            "a": {"b"},
            "b": {"c"},
            "c": set(),
        }
        result = transitive_closure(graph, {"a"})
        assert result == {"a", "b", "c"}

    def test_transitive_closure_handles_cycles(self):
        graph = {
            "a": {"b"},
            "b": {"a"},
        }
        result = transitive_closure(graph, {"a"})
        assert result == {"a", "b"}

    def test_transitive_closure_unknown_deps(self):
        """Deps not in the graph (no metadata) should still be included."""
        graph = {
            "a": {"b", "unknown_pkg"},
        }
        result = transitive_closure(graph, {"a"})
        assert result == {"a", "b", "unknown_pkg"}

    def test_transitive_closure_multiple_roots(self):
        graph = {
            "a": {"c"},
            "b": {"c"},
            "c": {"d"},
            "d": set(),
        }
        result = transitive_closure(graph, {"a", "b"})
        assert result == {"a", "b", "c", "d"}


class TestCoverageSets:
    def _make_downloads(self):
        return pd.DataFrame({
            "project": ["a", "b", "c", "d", "e"],
            "downloads": [500, 300, 100, 50, 50],
        })

    def test_coverage_thresholds(self):
        downloads = self._make_downloads()
        graph = {
            "a": {"x"},  # 'a' depends on 'x' which is not in top packages
            "b": set(),
            "c": set(),
            "d": set(),
            "e": set(),
        }
        results = compute_coverage_sets(downloads, graph, [0.80])
        r = results[0]
        # a=500 (50%), a+b=800 (80%) -> need top 2 packages
        assert r["top_packages_count"] == 2
        assert "x" in r["transitive_deps"]
        assert r["total_closure_size"] == 3  # a, b, x

    def test_closure_coverage_reflects_transitive(self):
        downloads = self._make_downloads()
        # 'a' depends on 'c', so the closure includes 'c' even though
        # we only needed 'a' for 50% coverage
        graph = {"a": {"c"}, "c": set()}
        results = compute_coverage_sets(downloads, graph, [0.50])
        r = results[0]
        # closure is {a, c}, coverage should include c's downloads
        assert r["closure_coverage"] == 600 / 1000  # a(500) + c(100)


class TestReport:
    def test_generates_file(self, tmp_path):
        downloads = pd.DataFrame({
            "project": ["a", "b"],
            "downloads": [1000, 500],
        })
        results = [{
            "threshold": 0.80,
            "top_packages_count": 1,
            "transitive_deps_count": 1,
            "total_closure_size": 2,
            "top_packages_downloads": 1000,
            "closure_downloads": 1200,
            "closure_coverage": 0.80,
            "total_downloads": 1500,
            "top_packages": ["a"],
            "transitive_deps": ["c"],
        }]
        output = tmp_path / "report.md"
        generate_report(results, downloads, output)
        assert output.exists()
        content = output.read_text()
        assert "80%" in content
        assert "| a |" in content
