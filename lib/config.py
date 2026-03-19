"""Configuration loading for markdown2confluence."""

import tomllib
from pathlib import Path

_LOCAL_CONFIG = "markdown2confluence.toml"
_CONFIG_PATHS = [
    Path(_LOCAL_CONFIG),
    Path.home() / ".config" / "markdown2confluence" / "config.toml",
]


def load_config():
    """Load config from the first existing TOML file.

    Search order: ./markdown2confluence.toml, ~/.config/markdown2confluence.toml.
    Returns (config_dict, config_path).
    """
    for path in _CONFIG_PATHS:
        if path.is_file():
            with open(path, "rb") as f:
                return tomllib.load(f), path
    locations = ", ".join(str(p) for p in _CONFIG_PATHS)
    raise FileNotFoundError(f"Config file not found. Expected one of: {locations}")
