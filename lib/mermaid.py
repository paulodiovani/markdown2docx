"""Mermaid diagram preprocessing -- renders mermaid code blocks to PNG via mmdc."""

import hashlib
import subprocess
import tempfile
from pathlib import Path

from lib.parser import walk_block_containers

TEMP_DIR = Path(tempfile.gettempdir()) / "markdown2docx"


MERMAID_THEMES = ("default", "neutral", "dark", "forest")


def _render_mermaid_to_png(raw, index, theme, transparent_bg):
    """Invoke mmdc to render mermaid source to a PNG; return the PNG path."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.md5(raw.encode()).hexdigest()[:10]
    name = f"mermaid_{index}_{digest}"
    mmd_path = TEMP_DIR / f"{name}.mmd"
    png_path = TEMP_DIR / f"{name}.png"

    mmd_path.write_text(raw)
    cmd = [
        "mmdc",
        "-i",
        str(mmd_path),
        "-o",
        str(png_path),
        "-w",
        "1024",
        "-H",
        "768",
        "-s",
        "2",
    ]
    if transparent_bg:
        cmd.extend(["-b", "transparent"])
    if theme:
        cmd.extend(["-t", theme])
    subprocess.run(cmd, check=True)
    return png_path


def preprocess_mermaid(tokens, base_dir, theme=None, transparent_bg=False):
    """Scan AST (including inside list items/blockquotes) for mermaid code
    blocks and replace them with image paragraph tokens.
    """
    # Shared counter so diagram indices remain unique across the whole document.
    counter = [0]

    def visit(token_list):
        result = []
        for token in token_list:
            if token.get("type") == "block_code":
                info = (
                    token.get("attrs", {}).get("info", "") if token.get("attrs") else ""
                )
                lang = info.split()[0] if info else ""
                if lang == "mermaid":
                    raw = token.get("raw", "") or token.get("text", "")
                    png_path = _render_mermaid_to_png(
                        raw, counter[0], theme, transparent_bg
                    )
                    counter[0] += 1
                    result.append(
                        {
                            "type": "paragraph",
                            "children": [
                                {
                                    "type": "image",
                                    "attrs": {
                                        "src": str(png_path),
                                        "alt": "mermaid diagram",
                                    },
                                }
                            ],
                        }
                    )
                    continue
            result.append(token)
        return result

    return walk_block_containers(tokens, visit)
