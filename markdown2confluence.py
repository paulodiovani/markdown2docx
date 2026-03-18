"""markdown2confluence -- Convert GitHub Flavored Markdown files to Confluence pages."""

from pathlib import Path

import click

from lib.alerts import preprocess_alerts
from lib.confluence import ConfluenceClient
from lib.mermaid import preprocess_mermaid
from lib.parser import create_parser, extract_text, preprocess_images


# ---------------------------------------------------------------------------
# ADF helpers
# ---------------------------------------------------------------------------


def _text(text, *marks):
    """Build an ADF text node, optionally with marks."""
    node = {"type": "text", "text": text}
    if marks:
        node["marks"] = list(marks)
    return node


def _mark(type_, **attrs):
    """Build an ADF mark dict."""
    m = {"type": type_}
    if attrs:
        m["attrs"] = attrs
    return m


def _add_mark(nodes, mark):
    """Return a copy of *nodes* with *mark* appended to every text node."""
    result = []
    for node in nodes:
        if node.get("type") == "text":
            new_node = {**node, "marks": node.get("marks", []) + [mark]}
            result.append(new_node)
        else:
            result.append(node)
    return result


# ---------------------------------------------------------------------------
# ADF renderer  (each render_* returns a list of ADF block nodes)
# ---------------------------------------------------------------------------


def render_to_adf(tokens, base_dir, **kw):
    """Render a token list to a complete ADF document dict."""
    content = []
    for token in tokens:
        content.extend(render_block(token, base_dir, **kw))
    return {"type": "doc", "version": 1, "content": content}


def render_block(token, base_dir, **kw):
    """Dispatch to render_{type}; always returns a list of ADF nodes."""
    dispatch = {
        "heading": render_heading,
        "paragraph": render_paragraph,
        "block_code": render_block_code,
        "block_quote": render_block_quote,
        "alert": render_alert,
        "list": render_list,
        "table": render_table,
        "thematic_break": render_thematic_break,
    }
    handler = dispatch.get(token["type"])
    return handler(token, base_dir, **kw) if handler else []


def render_heading(token, base_dir, **kw):
    level = token.get("attrs", {}).get("level", 1) if token.get("attrs") else 1
    content = render_inline(token.get("children", []), base_dir, **kw)
    return [{"type": "heading", "attrs": {"level": level}, "content": content}]


def render_paragraph(token, base_dir, client=None, page_id=None, uploaded=None, **kw):
    children = token.get("children", [])
    # Image-only paragraph → block image (implemented fully in task 5)
    if len(children) == 1 and children[0]["type"] == "image":
        return _render_image_block(
            children[0], base_dir, client=client, page_id=page_id, uploaded=uploaded
        )
    content = render_inline(
        children, base_dir, client=client, page_id=page_id, uploaded=uploaded, **kw
    )
    return [{"type": "paragraph", "content": content}] if content else []


def _render_image_block(token, base_dir, client=None, page_id=None, uploaded=None):
    """Placeholder; task 5 replaces this with a real mediaSingle node."""
    src = token.get("attrs", {}).get("src", "")
    alt = token.get("attrs", {}).get("alt", "") or src
    return [{"type": "paragraph", "content": [_text(f"[image: {alt}]")]}]


def render_block_code(token, base_dir, **kw):
    raw = token.get("raw", "") or token.get("text", "")
    info = token.get("attrs", {}).get("info", "") if token.get("attrs") else ""
    lang = info.split()[0] if info else ""
    node = {"type": "codeBlock", "content": [{"type": "text", "text": raw}]}
    if lang:
        node["attrs"] = {"language": lang}
    return [node]


def render_block_quote(token, base_dir, **kw):
    content = []
    for child in token.get("children", []):
        content.extend(render_block(child, base_dir, **kw))
    return [{"type": "blockquote", "content": content}]


def render_alert(token, base_dir, **kw):
    """Placeholder; task 7 replaces this with a Confluence panel extension."""
    content = []
    for child in token.get("children", []):
        content.extend(render_block(child, base_dir, **kw))
    return [{"type": "blockquote", "content": content}]


def render_list(token, base_dir, **kw):
    attrs = token.get("attrs", {}) or {}
    ordered = attrs.get("ordered", False)
    list_type = "orderedList" if ordered else "bulletList"
    items = []
    for item in token.get("children", []):
        item_children = item.get("children", [])
        is_task = item.get("type") == "task_list_item"
        checked = (
            item.get("attrs", {}).get("checked", False) if item.get("attrs") else False
        )
        item_content = []
        for j, child in enumerate(item_children):
            if child["type"] in ("paragraph", "block_text"):
                inline = render_inline(child.get("children", []), base_dir, **kw)
                if is_task and j == 0:
                    prefix = "\u2611 " if checked else "\u2610 "
                    inline = [_text(prefix)] + inline
                item_content.append({"type": "paragraph", "content": inline})
            elif child["type"] == "list":
                item_content.extend(render_list(child, base_dir, **kw))
            else:
                item_content.extend(render_block(child, base_dir, **kw))
        items.append({"type": "listItem", "content": item_content})
    node = {"type": list_type, "content": items}
    if ordered:
        node["attrs"] = {"order": 1}
    return [node]


def render_table(token, base_dir, **kw):
    """Placeholder; task 3 implements full table rendering."""
    return []


def render_thematic_break(token, base_dir, **kw):
    return [{"type": "rule"}]


# ---------------------------------------------------------------------------
# Inline renderer  (returns a list of ADF inline nodes)
# ---------------------------------------------------------------------------


def render_inline(children, base_dir, **kw):
    """Render inline token children to a list of ADF inline nodes."""
    if not children:
        return []
    nodes = []
    for child in children:
        t = child["type"]

        if t == "text":
            raw = (
                child.get("raw", "")
                or child.get("text", "")
                or child.get("children", "")
            )
            if isinstance(raw, list):
                raw = extract_text(raw)
            if raw:
                nodes.append(_text(raw))

        elif t == "strong":
            inner = render_inline(child.get("children", []), base_dir, **kw)
            nodes.extend(_add_mark(inner, _mark("strong")))

        elif t == "emphasis":
            inner = render_inline(child.get("children", []), base_dir, **kw)
            nodes.extend(_add_mark(inner, _mark("em")))

        elif t == "strikethrough":
            inner = render_inline(child.get("children", []), base_dir, **kw)
            nodes.extend(_add_mark(inner, _mark("strike")))

        elif t == "codespan":
            raw = child.get("raw", "") or child.get("text", "")
            if isinstance(raw, list):
                raw = extract_text(raw)
            nodes.append(_text(raw, _mark("code")))

        elif t == "link":
            attrs = child.get("attrs", {}) or {}
            url = attrs.get("url", "") or attrs.get("href", "")
            inner = render_inline(child.get("children", []), base_dir, **kw)
            if url:
                nodes.extend(_add_mark(inner, _mark("link", href=url)))

        elif t == "image":
            # Inline image placeholder (task 5 handles real uploads)
            alt = child.get("attrs", {}).get("alt", "")
            src = child.get("attrs", {}).get("src", "")
            nodes.append(_text(f"[image: {alt or src}]"))

        elif t == "softbreak":
            nodes.append(_text(" "))

        elif t == "linebreak":
            nodes.append({"type": "hardBreak"})

    return nodes


# ---------------------------------------------------------------------------
# Inline comment re-injection
# ---------------------------------------------------------------------------


def reapply_comment_marks(adf_doc, comments):
    """Best-effort re-application of inline comment annotation marks.

    For each open comment, ``inlineOriginalSelection`` is searched within every
    inline context (paragraph, heading, table cell).  When found, the matching
    text nodes receive an ``annotation`` mark so the comment stays anchored.

    Comments whose selection text spans block boundaries (e.g. a heading plus
    several list items) cannot be re-anchored automatically and are reported as
    warnings; Confluence will orphan them.
    """
    markers = {}
    for comment in comments:
        props = comment.get("properties", {})
        ref = props.get("inlineMarkerRef")
        selection = props.get("inlineOriginalSelection")
        if ref and selection:
            markers[ref] = selection

    if not markers:
        return adf_doc

    applied: set = set()
    _walk_and_inject(adf_doc.get("content", []), markers, applied)

    for ref, selection in markers.items():
        if ref not in applied:
            preview = selection[:40] + "…" if len(selection) > 40 else selection
            click.echo(
                f'  Warning: inline comment on "{preview}" could not be '
                f"re-anchored (text not found or spans block boundaries).",
                err=True,
            )

    return adf_doc


def _walk_and_inject(content, markers, applied):
    """Recursively walk ADF block nodes, injecting marks in inline contexts."""
    for node in content:
        node_type = node.get("type")
        node_content = node.get("content", [])
        if node_type in ("paragraph", "heading", "tableCell", "tableHeader"):
            _inject_into_inline(node_content, markers, applied)
        if node_content:
            _walk_and_inject(node_content, markers, applied)


def _inject_into_inline(inline_nodes, markers, applied):
    """Find comment selections in consecutive text nodes and add annotation marks.

    Builds a position map over all text nodes in *inline_nodes*, then for each
    unmatched marker checks whether its selection appears in the concatenated
    text.  All text nodes that overlap the match receive the annotation mark.
    """
    # Build position map: [(start, end, index)] for text nodes only
    pos_map = []
    full_text = ""
    for i, node in enumerate(inline_nodes):
        if node.get("type") == "text":
            t = node.get("text", "")
            pos_map.append((len(full_text), len(full_text) + len(t), i))
            full_text += t
        else:
            pos_map.append(None)

    for ref, selection in markers.items():
        if ref in applied:
            continue
        idx = full_text.find(selection)
        if idx == -1:
            continue

        sel_end = idx + len(selection)
        mark = _mark("annotation", annotationType="inlineComment", id=ref)

        for pos_info in pos_map:
            if pos_info is None:
                continue
            n_start, n_end, n_idx = pos_info
            if n_end <= idx or n_start >= sel_end:
                continue  # no overlap
            existing = inline_nodes[n_idx].get("marks", [])
            inline_nodes[n_idx]["marks"] = existing + [mark]

        applied.add(ref)


# ---------------------------------------------------------------------------
# Title extraction
# ---------------------------------------------------------------------------


def extract_title(tokens, fallback):
    """Return the text of the first h1 in the token list, or *fallback*."""
    for token in tokens:
        if token["type"] == "heading":
            level = token.get("attrs", {}).get("level", 1) if token.get("attrs") else 1
            if level == 1:
                return extract_text(token.get("children", []))
    return fallback


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def convert_file(input_path, client, page_id=None, parent_id=None, space_key=None):
    """Parse MD, render to ADF, re-apply comment marks, then create/update page."""
    input_path = Path(input_path)
    md_text = input_path.read_text(encoding="utf-8")
    base_dir = str(input_path.parent)

    md = create_parser()
    tokens = md(md_text)
    tokens = preprocess_mermaid(tokens, base_dir)
    tokens = preprocess_alerts(tokens)
    tokens = preprocess_images(tokens)

    if page_id:
        page = client.get_page(page_id)
        title = page["title"]
        version = page["version"]["number"]
        existing_attachments = client.get_attachments(page_id)

        adf_doc = render_to_adf(
            tokens,
            base_dir,
            client=client,
            page_id=page_id,
            uploaded=existing_attachments,
        )

        # Re-apply inline comment marks before overwriting the body
        comments = client.get_inline_comments(page_id)
        adf_doc = reapply_comment_marks(adf_doc, comments)

        result = client.update_page(page_id, version, title, adf_doc)
    else:
        title = extract_title(tokens, input_path.stem)
        # Create an empty page first so we have a page_id for attachment uploads
        result = client.create_page(parent_id, space_key, title)
        target_page_id = result["id"]

        adf_doc = render_to_adf(
            tokens,
            base_dir,
            client=client,
            page_id=target_page_id,
            uploaded={},
        )
        result = client.update_page(
            target_page_id, result["version"]["number"], title, adf_doc
        )

    return client.page_url(result)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    "--page-id",
    default=None,
    help="ID of an existing Confluence page to update.",
)
@click.option(
    "--parent-id",
    default=None,
    help="ID of the parent Confluence page under which to create a new page.",
)
@click.option(
    "--space-key",
    default=None,
    help="Confluence space key (required when creating a new page).",
)
def main(files, page_id, parent_id, space_key):
    """Convert one or more Markdown files to Confluence pages."""
    if not page_id and not parent_id:
        raise click.UsageError("One of --page-id or --parent-id is required.")
    if parent_id and not space_key:
        raise click.UsageError("--space-key is required when using --parent-id.")

    client = ConfluenceClient()

    for f in files:
        url = convert_file(
            f, client, page_id=page_id, parent_id=parent_id, space_key=space_key
        )
        click.echo(f"Published: {f} -> {url}")


if __name__ == "__main__":
    main()
