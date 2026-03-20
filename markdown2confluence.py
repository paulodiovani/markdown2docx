"""markdown2confluence -- Convert GitHub Flavored Markdown files to Confluence pages."""

import json
from collections import defaultdict
from pathlib import Path

import click

from lib.alerts import preprocess_alerts
from lib.confluence import ConfluenceClient
from lib.mermaid import MERMAID_THEMES, preprocess_mermaid
from lib.parser import (
    build_heading_anchor_map,
    create_parser,
    extract_text,
    preprocess_images,
    resolve_image_path,
)


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
    """Render a standalone image as an ADF mediaSingle node."""
    src = token.get("attrs", {}).get("src", "")
    alt = token.get("attrs", {}).get("alt", "") or src
    if not src:
        return []

    if client and page_id:
        img_path = resolve_image_path(src, base_dir)
        if img_path.exists():
            info = client.ensure_attachment(page_id, str(img_path), uploaded)
            node = _media_single(info, alt)
            if node:
                return [node]

    return [{"type": "paragraph", "content": [_text(f"[image: {alt}]")]}]


def _media_single(info, alt=""):
    """Build an ADF mediaSingle node from attachment media info.

    Returns None if the media_id or collection is missing (unexpected API
    response), so the caller can fall back to a placeholder.
    """
    media_id = info.get("media_id")
    collection = info.get("collection")
    if not media_id or not collection:
        return None
    return {
        "type": "mediaSingle",
        "attrs": {"layout": "center", "width": 100, "widthType": "percentage"},
        "content": [
            {
                "type": "media",
                "attrs": {
                    "id": media_id,
                    "type": "file",
                    "collection": collection,
                    "alt": alt,
                },
            }
        ],
    }


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


_ALERT_TO_PANEL = {
    "NOTE": "info",
    "TIP": "success",
    "IMPORTANT": "note",
    "WARNING": "warning",
    "CAUTION": "error",
}


def render_alert(token, base_dir, **kw):
    """Render a GitHub-style alert as a Confluence ADF panel node."""
    alert_type = (token.get("attrs") or {}).get("alert_type", "NOTE")
    panel_type = _ALERT_TO_PANEL.get(alert_type, "info")
    content = []
    for child in token.get("children", []):
        content.extend(render_block(child, base_dir, **kw))
    if not content:
        content = [{"type": "paragraph", "content": [_text("")]}]
    return [{"type": "panel", "attrs": {"panelType": panel_type}, "content": content}]


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
    """Render a GFM table to an ADF table node."""
    children = token.get("children", [])
    if not children:
        return []

    head = None
    body_rows = []
    for child in children:
        if child["type"] == "table_head":
            head = child
        elif child["type"] == "table_body":
            body_rows = child.get("children", [])

    # Collect column alignments from header cells (left/center/right/None)
    aligns = []
    if head:
        for cell in head.get("children", []):
            aligns.append((cell.get("attrs") or {}).get("align"))

    adf_rows = []

    if head:
        adf_rows.append(
            _table_row(head.get("children", []), aligns, True, base_dir, **kw)
        )
    for row in body_rows:
        adf_rows.append(
            _table_row(row.get("children", []), aligns, False, base_dir, **kw)
        )

    if not adf_rows:
        return []

    return [{"type": "table", "content": adf_rows}]


def _table_row(cells, aligns, is_header, base_dir, **kw):
    cell_type = "tableHeader" if is_header else "tableCell"
    adf_cells = []
    for i, cell in enumerate(cells):
        inline = render_inline(cell.get("children", []), base_dir, **kw)
        align = aligns[i] if i < len(aligns) else None
        para = {"type": "paragraph", "content": inline}
        if align in ("left", "center", "right"):
            para["attrs"] = {"alignment": align}
        adf_cells.append({"type": cell_type, "content": [para]})
    return {"type": "tableRow", "content": adf_cells}


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
            if url and url.startswith("#"):
                anchor_map = kw.get("anchor_map", {})
                slug = url[1:]
                anchor = anchor_map.get(slug, slug)
                nodes.extend(_add_mark(inner, _mark("link", href="#" + anchor)))
            elif url:
                nodes.extend(_add_mark(inner, _mark("link", href=url)))

        elif t == "image":
            src = child.get("attrs", {}).get("src", "")
            alt = child.get("attrs", {}).get("alt", "") or src
            client = kw.get("client")
            page_id = kw.get("page_id")
            uploaded = kw.get("uploaded")
            if client and page_id and src:
                img_path = resolve_image_path(src, base_dir)
                if img_path.exists():
                    info = client.ensure_attachment(page_id, str(img_path), uploaded)
                    node = _media_single(info, alt)
                    if node:
                        nodes.append(node)
                        continue
            nodes.append(_text(f"[image: {alt}]"))

        elif t == "softbreak":
            nodes.append(_text(" "))

        elif t == "linebreak":
            nodes.append({"type": "hardBreak"})

    return nodes


_SHORT_SELECTION = 20
_CONTEXT_CHARS = 30


# ---------------------------------------------------------------------------
# Inline comment re-injection
# ---------------------------------------------------------------------------


def _extract_comment_text(comment):
    """Extract plain text from a comment's ADF body."""
    body = comment.get("body", {}).get("atlas_doc_format", {}).get("value", "")
    if not body:
        return ""
    try:
        adf = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return ""
    parts = []

    def _walk(node):
        if isinstance(node, dict):
            if node.get("type") == "text":
                parts.append(node.get("text", ""))
            for child in node.get("content", []):
                _walk(child)

    _walk(adf)
    return "".join(parts)


def _truncate(text, max_len=50):
    """Truncate text with ellipsis."""
    return text[:max_len] + "…" if len(text) > max_len else text


def reapply_comment_marks(new_adf, old_adf, comments):
    """Re-apply inline comment annotation marks from old_adf onto new_adf.

    Uses a two-phase approach to handle both cross-block selections and
    duplicate text:

    **Phase 1 – structural anchor:** Walk old_adf to find where each
    annotation mark lives (block index + concatenated selection text, which
    naturally covers cross-block spans).  Search for that text in the new_adf
    near the same block index (±3 blocks) to tolerate insertions/deletions.

    **Phase 2 – global fallback:** If the structural search fails (content was
    moved far away), search the entire document.

    Comments whose text was deleted from the document are warned about and
    will be orphaned by Confluence.
    """
    # Primary source: extract annotation positions directly from old ADF body.
    # This gives us the actual current text (may differ from inlineOriginalSelection
    # if the page was edited after the comment was created).
    old_annotations = _extract_annotations_from_adf(old_adf)

    # Fallback source: inlineOriginalSelection from the comments API, used for
    # any UUID that appears in open comments but is already dangling in old ADF.
    api_selections = {}
    comment_texts = {}
    for c in comments:
        props = c.get("properties", {})
        ref = props.get("inlineMarkerRef")
        sel = props.get("inlineOriginalSelection")
        if ref and sel:
            api_selections[ref] = sel
        if ref:
            comment_texts[ref] = _extract_comment_text(c)

    if not old_annotations and not api_selections:
        return new_adf

    # Build a global flat text map over the new ADF once.
    text_nodes, global_text = _build_global_text_map(new_adf.get("content", []))

    applied: set = set()

    # Re-anchor comments found in old ADF body using expanding search.
    for uuid, info in old_annotations.items():
        selection = info["selection"]
        anchor = info["anchor_block"]
        context = info.get("context", ("", ""))
        if not selection:
            continue
        result = _apply_expanding_search(
            text_nodes,
            global_text,
            uuid,
            selection,
            anchor,
            applied,
            context=context,
        )
        if result["matched"]:
            delta = result["new_block"] - anchor
            if delta != 0:
                direction = "down" if delta > 0 else "up"
                click.echo(
                    f'  Comment on "{_truncate(selection)}" '
                    f"re-anchored (moved {abs(delta)} blocks {direction})",
                    err=True,
                )

    # Warn about open comments that could not be re-anchored.
    for uuid, sel in api_selections.items():
        if uuid not in applied:
            preview = _truncate(sel)
            body = _truncate(comment_texts.get(uuid, ""))
            if uuid not in old_annotations:
                click.echo(
                    f'  Warning: comment on "{preview}" was already '
                    f"dangling before this update — skipping.",
                    err=True,
                )
            else:
                click.echo(
                    f'  Warning: comment on "{preview}" could not be '
                    f"re-anchored (text not found).",
                    err=True,
                )
            if body:
                click.echo(f'           Comment: "{body}"', err=True)

    return new_adf


def _extract_annotations_from_adf(adf_doc):
    """Return ``{uuid: {"anchor_block", "selection", "context"}}`` from old ADF.

    Walks every text node collecting annotation marks.  Texts from multiple
    nodes (including cross-block spans) are concatenated in document order to
    reconstruct the full selection string.

    For short selections (≤ _SHORT_SELECTION chars), ``context`` is a
    ``(prefix, suffix)`` tuple of surrounding text from the old ADF.
    For longer selections it is ``("", "")``.
    """
    blocks = adf_doc.get("content", []) if adf_doc else []

    # Collect (uuid, block_idx, text) tuples in document order via DFS.
    entries = []
    for block_idx, block in enumerate(blocks):
        _collect_annotated_texts(block, block_idx, entries)

    # Group by UUID preserving insertion order.
    groups = defaultdict(lambda: {"block_indices": [], "texts": []})
    for uuid, block_idx, text in entries:
        groups[uuid]["block_indices"].append(block_idx)
        groups[uuid]["texts"].append(text)

    # Build old global text map for context extraction.
    old_text_nodes, old_global = _build_global_text_map(blocks)

    result = {}
    for uuid, info in groups.items():
        selection = "".join(info["texts"])
        anchor = info["block_indices"][0]
        context = ("", "")
        if len(selection) <= _SHORT_SELECTION and old_global:
            idx = old_global.find(selection)
            if idx != -1:
                prefix = old_global[max(0, idx - _CONTEXT_CHARS) : idx]
                suffix = old_global[
                    idx + len(selection) : idx + len(selection) + _CONTEXT_CHARS
                ]
                context = (prefix, suffix)
        result[uuid] = {
            "anchor_block": anchor,
            "selection": selection,
            "context": context,
        }
    return result


def _collect_annotated_texts(node, block_idx, entries):
    """DFS helper: appends ``(uuid, block_idx, text)`` for each annotated text node."""
    if node.get("type") == "text":
        for mark in node.get("marks", []):
            if mark.get("type") == "annotation":
                uuid = mark.get("attrs", {}).get("id")
                if uuid:
                    entries.append((uuid, block_idx, node.get("text", "")))
    for child in node.get("content", []):
        _collect_annotated_texts(child, block_idx, entries)


def _build_global_text_map(blocks):
    """Flatten all text nodes into ``(node_ref, block_idx, start, end)`` tuples.

    ``start``/``end`` are character offsets in the returned ``global_text``
    string, which is the concatenation of every text node in document order.
    Cross-block selections are naturally handled because all blocks share the
    same global coordinate space.
    """
    text_nodes = []
    pos = [0]

    def _walk(node, block_idx):
        if node.get("type") == "text":
            t = node.get("text", "")
            text_nodes.append((node, block_idx, pos[0], pos[0] + len(t)))
            pos[0] += len(t)
        for child in node.get("content", []):
            _walk(child, block_idx)

    for block_idx, block in enumerate(blocks):
        _walk(block, block_idx)

    global_text = "".join(n[0].get("text", "") for n in text_nodes)
    return text_nodes, global_text


def _context_matches(global_text, idx, selection, context):
    """Check if surrounding text at *idx* matches the expected context.

    For short selections, at least half the prefix/suffix characters must match
    the text surrounding the candidate position.  This tolerates light edits
    while preventing false matches on common words.
    """
    prefix, suffix = context
    if not prefix and not suffix:
        return True

    score = 0
    total = 0

    if prefix:
        actual_prefix = global_text[max(0, idx - len(prefix)) : idx]
        total += len(prefix)
        # Count matching chars from the end (closest to selection)
        for a, b in zip(reversed(actual_prefix), reversed(prefix)):
            if a == b:
                score += 1

    if suffix:
        sel_end = idx + len(selection)
        actual_suffix = global_text[sel_end : sel_end + len(suffix)]
        total += len(suffix)
        # Count matching chars from the start (closest to selection)
        for a, b in zip(actual_suffix, suffix):
            if a == b:
                score += 1

    return total > 0 and score >= total / 2


def _apply_expanding_search(
    text_nodes, global_text, uuid, selection, anchor_block, applied, context=None
):
    """Search for *selection* expanding outward from *anchor_block* block by block.

    Tries window sizes 0, 1, 2, … up to the full document extent.  The first
    match found is the one closest to the original position, so duplicate text
    elsewhere in the document is never preferred over a nearby occurrence.

    For short selections (≤ _SHORT_SELECTION chars) with *context*, candidate
    matches are verified against surrounding text before being accepted.

    Returns a dict ``{"matched": bool, "new_block": int}`` or
    ``{"matched": False}`` on failure.
    """
    if not text_nodes:
        return {"matched": False}

    need_context = len(selection) <= _SHORT_SELECTION and context and any(context)

    max_block = max(n[1] for n in text_nodes)
    max_window = max(anchor_block, max_block - anchor_block)

    prev_start = prev_end = None

    for window in range(max_window + 1):
        window_nodes = [n for n in text_nodes if abs(n[1] - anchor_block) <= window]
        if not window_nodes:
            continue

        win_start = window_nodes[0][2]
        win_end = window_nodes[-1][3]

        # Skip if this window covers the same text range as the previous one
        # (happens when intermediate blocks contain no text nodes, e.g. rule).
        if win_start == prev_start and win_end == prev_end:
            continue
        prev_start, prev_end = win_start, win_end

        # Search for all occurrences within this window.
        search_start = win_start
        while True:
            idx = global_text.find(selection, search_start, win_end)
            if idx == -1:
                break
            if need_context and not _context_matches(
                global_text, idx, selection, context
            ):
                search_start = idx + 1
                continue
            _apply_mark_at(text_nodes, uuid, idx, idx + len(selection), applied)
            # Find which block the match landed in.
            new_block = anchor_block
            for _, blk, start, end in text_nodes:
                if end > idx and start <= idx:
                    new_block = blk
                    break
            return {"matched": True, "new_block": new_block}

    return {"matched": False}


def _apply_mark_at(text_nodes, uuid, sel_start, sel_end, applied):
    """Add an annotation mark to every text node overlapping [sel_start, sel_end)."""
    mark = _mark("annotation", annotationType="inlineComment", id=uuid)
    matched = False
    for node_ref, _, start, end in text_nodes:
        if end > sel_start and start < sel_end:
            node_ref["marks"] = node_ref.get("marks", []) + [mark]
            matched = True
    if matched:
        applied.add(uuid)
    return matched


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


def convert_file(
    input_path,
    client,
    page_id=None,
    parent_id=None,
    space_key=None,
    theme=None,
    dry_run=False,
):
    """Parse MD, render to ADF, re-apply comment marks, then create/update page."""
    input_path = Path(input_path)
    md_text = input_path.read_text(encoding="utf-8")
    base_dir = str(input_path.parent)

    md = create_parser()
    tokens = md(md_text)
    tokens = preprocess_mermaid(tokens, base_dir, theme=theme)
    tokens = preprocess_alerts(tokens)
    tokens = preprocess_images(tokens)
    anchor_map = build_heading_anchor_map(tokens)

    if page_id:
        page = client.get_page(page_id)
        old_adf = client.get_page_adf(page)
        title = page["title"]
        version = page["version"]["number"]
        existing_attachments = client.get_attachments(page_id)

        adf_doc = render_to_adf(
            tokens,
            base_dir,
            client=client if not dry_run else None,
            page_id=page_id if not dry_run else None,
            uploaded=existing_attachments,
            anchor_map=anchor_map,
        )

        # Re-apply annotation marks: use old ADF for structural anchoring,
        # comments API as fallback for already-dangling marks.
        comments = client.get_inline_comments(page_id)
        adf_doc = reapply_comment_marks(adf_doc, old_adf, comments)

        if dry_run:
            return client.page_url(page)

        result = client.update_page(page_id, version, title, adf_doc)
    else:
        title = extract_title(tokens, input_path.stem)

        if dry_run:
            return None

        # Create an empty page first so we have a page_id for attachment uploads
        result = client.create_page(parent_id, space_key, title)
        target_page_id = result["id"]

        adf_doc = render_to_adf(
            tokens,
            base_dir,
            client=client,
            page_id=target_page_id,
            uploaded={},
            anchor_map=anchor_map,
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
@click.option(
    "--theme",
    type=click.Choice(MERMAID_THEMES),
    default=None,
    help="Mermaid diagram theme.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Parse and render without creating or updating pages.",
)
def main(files, page_id, parent_id, space_key, theme, dry_run):
    """Convert one or more Markdown files to Confluence pages."""
    if not page_id and not parent_id:
        raise click.UsageError("One of --page-id or --parent-id is required.")
    if parent_id and not space_key:
        raise click.UsageError("--space-key is required when using --parent-id.")

    client = ConfluenceClient()

    for f in files:
        url = convert_file(
            f,
            client,
            page_id=page_id,
            parent_id=parent_id,
            space_key=space_key,
            theme=theme,
            dry_run=dry_run,
        )
        prefix = "Dry run" if dry_run else "Published"
        if url:
            click.echo(f"{prefix}: {f} -> {url}")
        else:
            click.echo(f"{prefix}: {f}")


if __name__ == "__main__":
    main()
