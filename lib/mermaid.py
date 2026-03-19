"""Mermaid diagram preprocessing -- renders mermaid code blocks to PNG via mmdc."""

import hashlib
import subprocess
import tempfile
from pathlib import Path

TEMP_DIR = Path(tempfile.gettempdir()) / "markdown2docx"


MERMAID_THEMES = ("default", "neutral", "dark", "forest")


def preprocess_mermaid(tokens, base_dir, theme=None):
    """Scan AST for mermaid code blocks and replace with image paragraph tokens."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    diagram_index = 0

    for token in tokens:
        if token["type"] == "block_code":
            info = token.get("attrs", {}).get("info", "") if token.get("attrs") else ""
            lang = info.split()[0] if info else ""

            if lang == "mermaid":
                raw = token.get("raw", "") or token.get("text", "")
                digest = hashlib.md5(raw.encode()).hexdigest()[:10]
                name = f"mermaid_{diagram_index}_{digest}"
                diagram_index += 1
                mmd_path = TEMP_DIR / f"{name}.mmd"
                png_path = TEMP_DIR / f"{name}.png"

                mmd_path.write_text(raw)
                cmd = [
                    "mmdc",
                    "-i",
                    str(mmd_path),
                    "-o",
                    str(png_path),
                    "-b",
                    "transparent",
                    "-w",
                    "1024",
                    "-H",
                    "768",
                    "-s",
                    "2",
                ]
                if theme:
                    cmd.extend(["-t", theme])
                subprocess.run(cmd, check=True)

                # Replace with an image paragraph token
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
