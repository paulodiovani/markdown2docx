"""Mermaid diagram preprocessing -- renders mermaid code blocks to PNG via mmdc."""

import subprocess
import tempfile
from pathlib import Path

TEMP_DIR = Path(tempfile.gettempdir()) / "markdown2docx"


def preprocess_mermaid(tokens, base_dir):
    """Scan AST for mermaid code blocks and replace with image paragraph tokens."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    result = []

    for token in tokens:
        if token["type"] == "block_code":
            info = token.get("attrs", {}).get("info", "") if token.get("attrs") else ""
            lang = info.split()[0] if info else ""

            if lang == "mermaid":
                raw = token.get("raw", "") or token.get("text", "")
                mmd_path = TEMP_DIR / f"diagram_{id(token)}.mmd"
                png_path = TEMP_DIR / f"diagram_{id(token)}.png"

                mmd_path.write_text(raw)
                subprocess.run(
                    ["mmdc", "-i", str(mmd_path), "-o", str(png_path)],
                    check=True,
                )

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
