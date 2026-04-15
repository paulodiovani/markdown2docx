# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Two CLI tools that convert GitHub Flavored Markdown to different targets:

- `markdown2docx.py` -- renders to DOCX via python-docx
- `markdown2confluence.py` -- renders to ADF (Atlassian Document Format) and uploads to Confluence via REST API

Python 3.13.7 (see `.tool-versions`). Both tools share Markdown parsing and preprocessing in `lib/`.

## Commands

```bash
# Set up venv and install dependencies
make .venv
# or manually: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Build standalone executables into dist/ (requires PyInstaller)
make build

# Install built executables to ~/.local/bin
make install

# Lint / format
make lint      # ruff check .
make format    # ruff format .

# Run tools directly from source
.venv/bin/python markdown2docx.py <file.md> [-o output_dir]
.venv/bin/python markdown2confluence.py <file.md> --page-id <id>
.venv/bin/python markdown2confluence.py <file.md> --parent-id <id> --space-key <KEY>
```

No test suite is configured.

`markdown2confluence` requires a TOML config at `./markdown2confluence.toml` or `~/.config/markdown2confluence/config.toml` with `email`, `api_token`, `url`. See `markdown2confluence.toml.sample`.

## Architecture

Both tools follow the same pipeline, differing only in the render step:

1. **Parse** -- `lib.parser.create_parser()` builds a mistune v3 parser in AST mode (`renderer="ast"`) with GFM plugins (`table`, `strikethrough`, `task_lists`). Produces a list of token dicts.
2. **Preprocess** (mutate token list):
   - `lib.parser.preprocess_images()` -- normalizes image attrs (renames `url` → `src`)
   - `lib.mermaid.preprocess_mermaid()` -- renders `block_code` tokens with lang `mermaid` to PNG via `mmdc`, replaces them with image paragraph tokens
   - `lib.alerts.preprocess_alerts()` -- detects GitHub-style `[!NOTE]`/`[!TIP]`/`[!IMPORTANT]`/`[!WARNING]`/`[!CAUTION]` blockquotes and converts them to a custom `alert` token
3. **Render** -- a `render_*` function per token type:
   - `markdown2docx.py` walks the AST and mutates a `docx.Document`
   - `markdown2confluence.py` returns lists of ADF node dicts, assembled into a `{type: "doc", version: 1, content: [...]}` document
4. **Output**:
   - DOCX: written as `<filename>.docx` into the output directory
   - Confluence: uploaded via `lib.confluence.ConfluenceClient` (create or update page; attachments uploaded separately and referenced by `mediaSingle` nodes)

## Key Design Decisions

- **No classes except `ConfluenceClient`.** All rendering logic is pure functions. DOCX functions that mutate the `Document` receive it as an explicit parameter.
- **`lib/` holds only code shared between the two tools.** Tool-specific rendering stays in the top-level `.py` file.
- **Mistune AST quirks**: `table_head` contains cells directly (it IS the header row), while `table_body` contains `table_row` children. List items use `block_text` children (not `paragraph`). Task list items have type `task_list_item`. `[!NOTE]` etc. are split across two text nodes (`"["` and `"!NOTE]"`) -- see `lib.alerts.detect_alert_type`.
- **Custom `alert` token type**: inserted by `preprocess_alerts`; each renderer has its own `render_alert` (DOCX = shaded/bordered paragraph, Confluence = `panel` ADF node).
- **DOCX XML manipulation**: python-docx lacks native APIs for hyperlinks, internal anchors/bookmarks, paragraph shading, and borders. These use `OxmlElement` and `qn()` to build raw OOXML elements.
- **Pygments token hierarchy**: `get_token_style()` walks up `.parent` chain to find a matching style in `TOKEN_STYLES`.
- **Images are block-level in DOCX**: All images use `doc.add_picture()` which creates a new paragraph.
- **Code blocks without language**: Use `TextLexer` (no highlighting) rather than `guess_lexer`.
- **Confluence attachment dedup**: `ConfluenceClient.ensure_attachment()` stores an MD5 of each uploaded file in the attachment `comment` field and skips re-upload when the hash matches, so unchanged images and deterministic mermaid output don't cause churn.
- **Do NOT catch errors.** Let exceptions propagate naturally. If a dependency is missing or something fails, the user should see the error.

## Dependencies

- **mistune** (v3.x) -- Markdown parser in AST mode
- **python-docx** (v1.x) -- DOCX generation
- **Pygments** (v2.x) -- Syntax highlighting for code blocks (DOCX only; Confluence emits a raw `codeBlock` ADF node)
- **click** (v8.x) -- CLI framework
- **requests** (v2.x) -- Confluence REST API calls
- **ruff** -- lint + format (config in `ruff.toml`)
- **PyInstaller** (build-time only) -- standalone executable bundling, invoked by `make build`
- **mmdc** (optional, external) -- Mermaid CLI for diagram rendering
