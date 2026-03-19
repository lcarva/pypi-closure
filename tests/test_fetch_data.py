"""Tests for fetch_data.py."""

from pathlib import Path

import responses

from fetch_data import CLICKHOUSE_URL, fetch_downloads, fetch_deps, query_clickhouse


SAMPLE_DOWNLOADS_CSV = """\
"project","downloads"
"boto3",1000000
"requests",900000
"urllib3",800000
"""

SAMPLE_DEPS_CSV = """\
"name","version","requires_dist"
"requests","2.31.0","['urllib3>=1.21.1','charset-normalizer>=2','idna>=2.5','certifi>=2017.4.17']"
"boto3","1.28.0","['botocore>=1.31.0','jmespath>=0.7.1','s3transfer>=0.6.0']"
"""


@responses.activate
def test_query_clickhouse():
    responses.add(responses.POST, CLICKHOUSE_URL, body="ok\n", status=200)
    result = query_clickhouse("SELECT 1")
    assert result == "ok\n"
    assert "SELECT 1" in responses.calls[0].request.body.decode()


@responses.activate
def test_query_clickhouse_error():
    responses.add(responses.POST, CLICKHOUSE_URL, body="error", status=500)
    try:
        query_clickhouse("SELECT 1")
        assert False, "Should have raised"
    except Exception:
        pass


@responses.activate
def test_fetch_downloads(tmp_path):
    responses.add(responses.POST, CLICKHOUSE_URL, body=SAMPLE_DOWNLOADS_CSV, status=200)
    output = tmp_path / "downloads.csv"
    packages = fetch_downloads(output)
    assert packages == ["boto3", "requests", "urllib3"]
    assert output.exists()
    content = output.read_text()
    assert "boto3" in content
    assert "requests" in content


@responses.activate
def test_fetch_deps(tmp_path):
    responses.add(responses.POST, CLICKHOUSE_URL, body=SAMPLE_DEPS_CSV, status=200)
    output = tmp_path / "deps.csv"
    count = fetch_deps(["requests", "boto3"], output)
    assert count == 2
    assert output.exists()
    content = output.read_text()
    assert "requests" in content
    assert "urllib3" in content
