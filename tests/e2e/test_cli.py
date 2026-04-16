"""End-to-end tests for the ``main`` CLI entry points.

Uses ``click.testing.CliRunner`` so we exercise argument parsing, option
validation, and the happy path of each CLI without touching the network.
"""

import json
from pathlib import Path

import responses
from click.testing import CliRunner

import markdown2confluence as m2c
import markdown2docx as m2d


EXAMPLES = Path(__file__).resolve().parent.parent.parent / "examples"
BASE_URL = "https://test.atlassian.net"


# ---------------------------------------------------------------------------
# markdown2docx CLI
# ---------------------------------------------------------------------------


def test_docx_cli_converts_file(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        m2d.main,
        [str(EXAMPLES / "basic.md"), "-o", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert "Converted:" in result.output
    assert (tmp_path / "basic.md.docx").exists()


def test_docx_cli_requires_file_argument():
    runner = CliRunner()
    result = runner.invoke(m2d.main, [])
    assert result.exit_code != 0
    assert "Missing argument" in result.output or "Usage" in result.output


# ---------------------------------------------------------------------------
# markdown2confluence CLI
# ---------------------------------------------------------------------------


def _register_noop(page_id="P1"):
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/rest/api/content/{page_id}",
        json={
            "id": page_id,
            "title": "T",
            "version": {"number": 1},
            "body": {
                "atlas_doc_format": {
                    "value": json.dumps({"type": "doc", "version": 1, "content": []})
                }
            },
            "_links": {"base": BASE_URL, "webui": f"/wiki/spaces/X/pages/{page_id}"},
        },
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/rest/api/content/{page_id}/child/attachment",
        json={"results": []},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/api/v2/pages/{page_id}/inline-comments",
        json={"results": []},
        status=200,
    )
    responses.add(
        responses.PUT,
        f"{BASE_URL}/wiki/rest/api/content/{page_id}",
        json={
            "id": page_id,
            "title": "T",
            "version": {"number": 2},
            "_links": {"base": BASE_URL, "webui": f"/wiki/spaces/X/pages/{page_id}"},
        },
        status=200,
    )


@responses.activate
def test_confluence_cli_publishes_update(mock_confluence_config):
    _register_noop("P1")
    runner = CliRunner()
    result = runner.invoke(m2c.main, [str(EXAMPLES / "basic.md"), "--page-id", "P1"])
    assert result.exit_code == 0, result.output
    assert "Published:" in result.output
    assert "P1" in result.output


def test_confluence_cli_dry_run_create(mock_confluence_config):
    runner = CliRunner()
    result = runner.invoke(
        m2c.main,
        [
            str(EXAMPLES / "basic.md"),
            "--parent-id",
            "PARENT",
            "--space-key",
            "SP",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Dry run:" in result.output


def test_confluence_cli_requires_page_or_parent(mock_confluence_config):
    runner = CliRunner()
    result = runner.invoke(m2c.main, [str(EXAMPLES / "basic.md")])
    assert result.exit_code != 0
    assert "--page-id" in result.output or "--parent-id" in result.output


def test_confluence_cli_parent_requires_space_key(mock_confluence_config):
    runner = CliRunner()
    result = runner.invoke(
        m2c.main, [str(EXAMPLES / "basic.md"), "--parent-id", "PARENT"]
    )
    assert result.exit_code != 0
    assert "--space-key" in result.output
