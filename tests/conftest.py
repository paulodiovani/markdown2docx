"""Shared pytest fixtures for the markdown2docx test suite."""

from pathlib import Path

import pytest


@pytest.fixture
def parse_markdown():
    """Return a mistune AST parser built via ``lib.parser.create_parser``."""
    from lib.parser import create_parser

    return create_parser()


@pytest.fixture
def make_doc():
    """Factory that returns a fresh ``docx.Document``."""
    from docx import Document

    def _make():
        return Document()

    return _make


@pytest.fixture
def mock_confluence_config(monkeypatch):
    """Patch ``lib.confluence.load_config`` to return test credentials."""
    config = {
        "email": "test@example.com",
        "api_token": "test-token",
        "url": "https://test.atlassian.net",
    }
    path = Path("/fake/config.toml")

    def fake_load_config():
        return config, path

    monkeypatch.setattr("lib.confluence.load_config", fake_load_config)
    return config


@pytest.fixture
def small_jpeg(tmp_path):
    """Copy ``examples/cat.jpg`` into ``tmp_path`` and return its path.

    Uses a real JPEG from the repo so tests don't need Pillow as a dev dep.
    """
    import shutil

    src = Path(__file__).resolve().parent.parent / "examples" / "cat.jpg"
    dest = tmp_path / "small.jpg"
    shutil.copy(src, dest)
    return dest
