# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Single-file CLI tool that converts GitHub Flavored Markdown to DOCX. Python 3.13.7 (see `.tool-versions`).

## Commands

```bash
# Install dependencies
.venv/bin/pip install -r requirements.txt

# Run conversion
.venv/bin/python markdown2docx.py <file.md> [-o output_dir]

# Run with multiple files
.venv/bin/python markdown2docx.py file1.md file2.md -o ./output
```

No test suite or linter is configured.

## Architecture

Everything lives in `markdown2docx.py`. The pipeline is:

1. **Parse**: mistune v3 in AST mode (`renderer="ast"`) with GFM plugins (table, strikethrough, task_lists) produces a list of token dicts
2. **Preprocess**: `preprocess_mermaid()` scans for `block_code` tokens with lang `mermaid`, renders them to PNG via `mmdc`, replaces with image paragraph tokens
3. **Render**: `render_tokens()` walks the AST, dispatches each block token to a `render_*` function that builds DOCX elements via python-docx
4. **Save**: Output as `<filename>.docx` in the output directory

## Key Design Decisions

- **No classes.** All logic is pure functions. Functions that mutate the `Document` receive it as an explicit parameter.
- **Mistune AST quirks**: `table_head` contains cells directly (it IS the header row), while `table_body` contains `table_row` children. List items use `block_text` children (not `paragraph`). Task list items have type `task_list_item`.
- **DOCX XML manipulation**: python-docx lacks native APIs for hyperlinks, paragraph shading, and borders. These use `OxmlElement` and `qn()` to build raw OOXML elements.
- **Pygments token hierarchy**: `get_token_style()` walks up `.parent` chain to find a matching style in `TOKEN_STYLES`.
- **Images are block-level**: All images use `doc.add_picture()` which creates a new paragraph.
- **Code blocks without language**: Use `TextLexer` (no highlighting) rather than `guess_lexer`.

## Dependencies

- **mistune** (v3.x) -- Markdown parser in AST mode
- **python-docx** (v1.x) -- DOCX generation
- **Pygments** (v2.x) -- Syntax highlighting for code blocks
- **click** (v8.x) -- CLI framework
- **mmdc** (optional) -- Mermaid CLI for diagram rendering
