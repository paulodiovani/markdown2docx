"""Unit tests for lib.config."""

from pathlib import Path

import pytest

from lib.config import load_config


def _write_toml(path, email="a@b.com", token="tok", url="https://u.example"):
    path.write_text(
        f'email = "{email}"\napi_token = "{token}"\nurl = "{url}"\n',
    )


def test_load_config_reads_local_file(tmp_path, monkeypatch):
    local = tmp_path / "local.toml"
    _write_toml(local, email="local@x.com")
    monkeypatch.setattr("lib.config._CONFIG_PATHS", [local])
    config, path = load_config()
    assert config == {
        "email": "local@x.com",
        "api_token": "tok",
        "url": "https://u.example",
    }
    assert path == local


def test_load_config_local_wins_over_home(tmp_path, monkeypatch):
    local = tmp_path / "local.toml"
    home = tmp_path / "home.toml"
    _write_toml(local, email="local@x.com")
    _write_toml(home, email="home@x.com")
    monkeypatch.setattr("lib.config._CONFIG_PATHS", [local, home])
    config, path = load_config()
    assert config["email"] == "local@x.com"
    assert path == local


def test_load_config_falls_back_to_home(tmp_path, monkeypatch):
    missing_local = tmp_path / "nope.toml"
    home = tmp_path / "home.toml"
    _write_toml(home, email="home@x.com")
    monkeypatch.setattr("lib.config._CONFIG_PATHS", [missing_local, home])
    config, path = load_config()
    assert config["email"] == "home@x.com"
    assert path == home


def test_load_config_raises_when_no_file_exists(tmp_path, monkeypatch):
    missing1 = tmp_path / "a.toml"
    missing2 = tmp_path / "b.toml"
    monkeypatch.setattr("lib.config._CONFIG_PATHS", [missing1, missing2])
    with pytest.raises(FileNotFoundError) as excinfo:
        load_config()
    message = str(excinfo.value)
    assert "a.toml" in message
    assert "b.toml" in message


def test_load_config_returns_path_object(tmp_path, monkeypatch):
    local = tmp_path / "c.toml"
    _write_toml(local)
    monkeypatch.setattr("lib.config._CONFIG_PATHS", [local])
    _, path = load_config()
    assert isinstance(path, Path)
