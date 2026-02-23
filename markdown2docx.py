"""markdown2docx -- Convert GitHub Flavored Markdown files to DOCX format."""

import os
import subprocess
import tempfile
from pathlib import Path

import click
import mistune
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from pygments import lex
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.token import (
    Comment,
    Error,
    Generic,
    Keyword,
    Literal,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Token,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEMP_DIR = Path(tempfile.gettempdir()) / "markdown2docx"

CODE_FONT = "Courier New"
CODE_FONT_SIZE = Pt(9)
CODE_BG_COLOR = "F2F2F2"
MAX_IMAGE_WIDTH = Inches(6)

# Pygments token type -> (hex_color, bold, italic)
TOKEN_STYLES = {
    Comment: ("6A9955", False, True),
    Comment.Preproc: ("C586C0", True, False),
    Keyword: ("569CD6", True, False),
    Keyword.Constant: ("569CD6", True, False),
    Keyword.Type: ("4EC9B0", False, False),
    Name.Builtin: ("DCDCAA", False, False),
    Name.Function: ("DCDCAA", False, False),
    Name.Class: ("4EC9B0", True, False),
    Name.Decorator: ("DCDCAA", False, False),
    Name.Exception: ("4EC9B0", False, False),
    Name.Tag: ("569CD6", False, False),
    Name.Attribute: ("9CDCFE", False, False),
    String: ("CE9178", False, False),
    Number: ("B5CEA8", False, False),
    Literal: ("CE9178", False, False),
    Operator: ("D4D4D4", False, False),
    Operator.Word: ("569CD6", True, False),
    Punctuation: ("D4D4D4", False, False),
    Generic.Heading: ("569CD6", True, False),
    Generic.Subheading: ("569CD6", True, False),
    Generic.Emph: (None, False, True),
    Generic.Strong: (None, True, False),
    Generic.Error: ("F44747", False, False),
    Error: ("F44747", False, False),
}

# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------


def extract_text(children):
    """Recursively extract plain text from token children."""
    if children is None:
        return ""
    parts = []
    for child in children:
        if child.get("raw"):
            parts.append(child["raw"])
        elif child.get("text"):
            parts.append(child["text"])
        elif child.get("children"):
            parts.append(extract_text(child["children"]))
    return "".join(parts)


def get_token_style(token_type):
    """Walk Pygments token hierarchy to find matching style."""
    t = token_type
    while t is not Token:
        if t in TOKEN_STYLES:
            return TOKEN_STYLES[t]
        t = t.parent
    return None


def resolve_image_path(url, base_dir):
    """Resolve image path relative to base_dir or as absolute."""
    if os.path.isabs(url):
        return Path(url)
    return Path(base_dir) / url


# ---------------------------------------------------------------------------
# Side-effect functions (mutate doc or paragraph)
# ---------------------------------------------------------------------------


def set_paragraph_shading(paragraph, color_hex):
    """Set background shading on a paragraph via XML manipulation."""
    p_pr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color_hex)
    p_pr.append(shd)


def add_hyperlink(paragraph, url, text):
    """Add a clickable hyperlink to a paragraph via XML manipulation."""
    part = paragraph.part
    r_id = part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    run_elem = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")

    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    rPr.append(color)

    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    rPr.append(underline)

    run_elem.append(rPr)

    text_elem = OxmlElement("w:t")
    text_elem.set(qn("xml:space"), "preserve")
    text_elem.text = text
    run_elem.append(text_elem)

    hyperlink.append(run_elem)
    paragraph._p.append(hyperlink)


def add_image(doc, url, base_dir):
    """Resolve image path and add picture to document with max width."""
    img_path = resolve_image_path(url, base_dir)
    if not img_path.exists():
        doc.add_paragraph(f"[Image not found: {url}]")
        return
    doc.add_picture(str(img_path), width=MAX_IMAGE_WIDTH)


# ---------------------------------------------------------------------------
# Rendering functions
# ---------------------------------------------------------------------------


def render_tokens(doc, tokens, base_dir):
    """Iterate top-level tokens and dispatch each."""
    for token in tokens:
        render_block(doc, token, base_dir)


def render_block(doc, token, base_dir):
    """Dispatch to render_{type} by token type."""
    t = token["type"]
    dispatch = {
        "heading": render_heading,
        "paragraph": render_paragraph,
        "block_code": render_block_code,
        "block_quote": render_block_quote,
        "list": render_list,
        "table": render_table,
        "thematic_break": render_thematic_break,
    }
    handler = dispatch.get(t)
    if handler:
        if t in ("block_code", "thematic_break"):
            handler(doc, token)
        else:
            handler(doc, token, base_dir)


def render_heading(doc, token, base_dir):
    """Render a heading token."""
    level = token.get("attrs", {}).get("level", 1) if token.get("attrs") else 1
    heading = doc.add_heading(level=level)
    render_inline(heading, token.get("children", []), base_dir)


def render_paragraph(doc, token, base_dir):
    """Render a paragraph token with inline children."""
    children = token.get("children", [])

    # Check if paragraph contains only an image
    if len(children) == 1 and children[0]["type"] == "image":
        img = children[0]
        src = img.get("attrs", {}).get("src", "") if img.get("attrs") else ""
        if src:
            add_image(doc, src, base_dir)
        return

    para = doc.add_paragraph()
    render_inline(para, children, base_dir)


def render_block_code(doc, token):
    """Render a code block with Pygments syntax highlighting."""
    raw = token.get("raw", "") or token.get("text", "")
    info = token.get("attrs", {}).get("info", "") if token.get("attrs") else ""
    lang = info.split()[0] if info else ""

    # Strip trailing newline for cleaner rendering
    if raw.endswith("\n"):
        raw = raw[:-1]

    try:
        lexer = get_lexer_by_name(lang) if lang else TextLexer()
    except Exception:
        lexer = TextLexer()

    para = doc.add_paragraph()
    set_paragraph_shading(para, CODE_BG_COLOR)

    tokens_list = list(lex(raw, lexer))
    for token_type, value in tokens_list:
        if not value:
            continue
        run = para.add_run(value)
        run.font.name = CODE_FONT
        run.font.size = CODE_FONT_SIZE

        style = get_token_style(token_type)
        if style:
            color_hex, bold, italic = style
            if color_hex:
                run.font.color.rgb = RGBColor.from_string(color_hex)
            run.bold = bold
            run.italic = italic


def render_block_quote(doc, token, base_dir):
    """Render a blockquote with left indentation and gray left border."""
    children = token.get("children", [])
    for child in children:
        if child["type"] == "paragraph":
            para = doc.add_paragraph()

            # Add left indentation
            p_fmt = para.paragraph_format
            p_fmt.left_indent = Inches(0.5)

            # Add gray left border via XML
            p_pr = para._p.get_or_add_pPr()
            p_bdr = OxmlElement("w:pBdr")
            left_bdr = OxmlElement("w:left")
            left_bdr.set(qn("w:val"), "single")
            left_bdr.set(qn("w:sz"), "12")
            left_bdr.set(qn("w:space"), "4")
            left_bdr.set(qn("w:color"), "999999")
            p_bdr.append(left_bdr)
            p_pr.append(p_bdr)

            render_inline(para, child.get("children", []), base_dir)
        else:
            render_block(doc, child, base_dir)


def render_list(doc, token, base_dir):
    """Render ordered, unordered, and task lists."""
    attrs = token.get("attrs", {}) or {}
    ordered = attrs.get("ordered", False)
    children = token.get("children", [])

    for i, item in enumerate(children):
        item_children = item.get("children", [])

        # Determine style
        style = "List Number" if ordered else "List Bullet"

        # Check for task list item (type is task_list_item)
        is_task = item.get("type") == "task_list_item"
        checked = item.get("attrs", {}).get("checked", False) if item.get("attrs") else False

        for j, child in enumerate(item_children):
            if child["type"] in ("paragraph", "block_text"):
                para = doc.add_paragraph(style=style)
                if is_task and j == 0:
                    checkbox = "\u2611 " if checked else "\u2610 "
                    para.add_run(checkbox)
                render_inline(para, child.get("children", []), base_dir)
            elif child["type"] == "list":
                render_list(doc, child, base_dir)
            else:
                render_block(doc, child, base_dir)


def render_table(doc, token, base_dir):
    """Render a table with Table Grid style, bold headers, and alignment."""
    children = token.get("children", [])
    if not children:
        return

    # Find head and body -- table_head IS a row (contains cells directly),
    # table_body contains table_row children
    head = None
    body_rows = []
    for child in children:
        if child["type"] == "table_head":
            head = child
        elif child["type"] == "table_body":
            body_rows = child.get("children", [])

    # Build list of (cells_list, is_header) tuples
    all_rows = []
    if head:
        all_rows.append((head.get("children", []), True))
    for row in body_rows:
        all_rows.append((row.get("children", []), False))

    if not all_rows:
        return

    num_cols = len(all_rows[0][0])
    num_rows = len(all_rows)

    table = doc.add_table(rows=num_rows, cols=num_cols, style="Table Grid")

    # Get column alignments from head cells
    aligns = []
    if head:
        for cell_token in head.get("children", []):
            cell_attrs = cell_token.get("attrs", {}) or {}
            aligns.append(cell_attrs.get("align"))

    align_map = {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
    }

    for row_idx, (cells_list, is_header) in enumerate(all_rows):

        for col_idx, cell_token in enumerate(cells_list):
            cell = table.rows[row_idx].cells[col_idx]
            para = cell.paragraphs[0]

            cell_children = cell_token.get("children", [])
            render_inline(para, cell_children, base_dir, bold=is_header)

            # Apply alignment
            if col_idx < len(aligns) and aligns[col_idx] in align_map:
                para.alignment = align_map[aligns[col_idx]]


def render_thematic_break(doc, token):
    """Render a horizontal rule as a paragraph with bottom border."""
    para = doc.add_paragraph()
    p_pr = para._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom_bdr = OxmlElement("w:bottom")
    bottom_bdr.set(qn("w:val"), "single")
    bottom_bdr.set(qn("w:sz"), "6")
    bottom_bdr.set(qn("w:space"), "1")
    bottom_bdr.set(qn("w:color"), "auto")
    p_bdr.append(bottom_bdr)
    p_pr.append(p_bdr)


def render_inline(paragraph, children, base_dir, bold=False, italic=False, strike=False):
    """Recursive inline renderer for text, strong, emphasis, code, links, images, etc."""
    if children is None:
        return

    for child in children:
        t = child["type"]

        if t == "text":
            raw = child.get("raw", "") or child.get("text", "") or child.get("children", "")
            if isinstance(raw, list):
                raw = extract_text(raw)
            run = paragraph.add_run(raw)
            if bold:
                run.bold = True
            if italic:
                run.italic = True
            if strike:
                run.font.strike = True

        elif t == "strong":
            render_inline(
                paragraph,
                child.get("children", []),
                base_dir,
                bold=True,
                italic=italic,
                strike=strike,
            )

        elif t == "emphasis":
            render_inline(
                paragraph,
                child.get("children", []),
                base_dir,
                bold=bold,
                italic=True,
                strike=strike,
            )

        elif t == "strikethrough":
            render_inline(
                paragraph,
                child.get("children", []),
                base_dir,
                bold=bold,
                italic=italic,
                strike=True,
            )

        elif t == "codespan":
            raw = child.get("raw", "") or child.get("text", "") or child.get("children", "")
            if isinstance(raw, list):
                raw = extract_text(raw)
            run = paragraph.add_run(raw)
            run.font.name = CODE_FONT
            run.font.size = CODE_FONT_SIZE
            if bold:
                run.bold = True
            if italic:
                run.italic = True

        elif t == "link":
            attrs = child.get("attrs", {}) or {}
            url = attrs.get("url", "") or attrs.get("href", "")
            link_text = extract_text(child.get("children", []))
            if url:
                add_hyperlink(paragraph, url, link_text)

        elif t == "image":
            attrs = child.get("attrs", {}) or {}
            src = attrs.get("src", "") or attrs.get("url", "")
            if src:
                add_image(paragraph._parent, src, base_dir)

        elif t == "softbreak":
            paragraph.add_run("\n")

        elif t == "linebreak":
            run = paragraph.add_run()
            run.add_break()


# ---------------------------------------------------------------------------
# Mermaid preprocessing
# ---------------------------------------------------------------------------


def preprocess_mermaid(tokens, base_dir):
    """Scan AST for mermaid code blocks and replace with image paragraphs."""
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
                    capture_output=True,
                )

                # Replace with an image paragraph token
                result.append(
                    {
                        "type": "paragraph",
                        "children": [
                            {
                                "type": "image",
                                "attrs": {"src": str(png_path), "alt": "mermaid diagram"},
                            }
                        ],
                    }
                )
                continue

        result.append(token)

    return result


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def convert_file(input_path, output_dir):
    """Read MD, parse to AST, preprocess mermaid, render DOCX, save, return output path."""
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    md_text = input_path.read_text(encoding="utf-8")
    base_dir = str(input_path.parent)

    # Parse to AST with GFM plugins
    md = mistune.create_markdown(
        renderer="ast",
        plugins=["table", "strikethrough", "task_lists"],
    )
    tokens = md(md_text)

    # Preprocess mermaid diagrams (silently skip if mmdc not available)
    try:
        tokens = preprocess_mermaid(tokens, base_dir)
    except FileNotFoundError:
        pass  # mmdc not installed, leave mermaid blocks as code

    # Create document and render
    doc = Document()
    render_tokens(doc, tokens, base_dir)

    # Save
    output_path = output_dir / f"{input_path.name}.docx"
    doc.save(str(output_path))
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    "--output",
    "-o",
    default="./output",
    type=click.Path(),
    help="Output directory (default: ./output)",
)
def main(files, output):
    """Convert one or more Markdown files to DOCX format."""
    for f in files:
        out = convert_file(f, output)
        click.echo(f"Converted: {f} -> {out}")


if __name__ == "__main__":
    main()
