"""markdown2confluence -- Convert GitHub Flavored Markdown files to Confluence pages."""

import html
from pathlib import Path

import click

from lib.alerts import preprocess_alerts
from lib.confluence import ConfluenceClient
from lib.mermaid import preprocess_mermaid
from lib.parser import (
    create_parser,
    extract_text,
    preprocess_images,
    resolve_image_path,
)


# ---------------------------------------------------------------------------
# Storage format renderer
# ---------------------------------------------------------------------------


def render_tokens(tokens, base_dir, client=None, page_id=None, uploaded=None):
    """Render all top-level tokens to a Confluence storage format string."""
    return "".join(
        render_block(t, base_dir, client=client, page_id=page_id, uploaded=uploaded)
        for t in tokens
    )


def render_block(token, base_dir, client=None, page_id=None, uploaded=None):
    """Dispatch to render_{type} by token type."""
    t = token["type"]
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
    handler = dispatch.get(t)
    if handler:
        return handler(
            token, base_dir, client=client, page_id=page_id, uploaded=uploaded
        )
    return ""


def render_heading(token, base_dir, **kwargs):
    """Render a heading token to <h1>…<h6>."""
    level = token.get("attrs", {}).get("level", 1) if token.get("attrs") else 1
    inner = render_inline(token.get("children", []), base_dir, **kwargs)
    return f"<h{level}>{inner}</h{level}>"


def render_paragraph(
    token, base_dir, client=None, page_id=None, uploaded=None, **kwargs
):
    """Render a paragraph token to <p>…</p>, handling image-only paragraphs."""
    children = token.get("children", [])

    # Image-only paragraph: render as a block image
    if len(children) == 1 and children[0]["type"] == "image":
        return render_image_block(
            children[0], base_dir, client=client, page_id=page_id, uploaded=uploaded
        )

    inner = render_inline(
        children, base_dir, client=client, page_id=page_id, uploaded=uploaded
    )
    if inner:
        return f"<p>{inner}</p>"
    return ""


def render_image_block(token, base_dir, client=None, page_id=None, uploaded=None):
    """Render a standalone image token as a Confluence attachment or placeholder."""
    src = token.get("attrs", {}).get("src", "")
    alt = token.get("attrs", {}).get("alt", "")
    if not src:
        return ""

    if client and page_id:
        img_path = resolve_image_path(src, base_dir)
        if img_path.exists():
            filename = client.ensure_attachment(page_id, str(img_path), uploaded)
            return (
                f'<p><ac:image ac:alt="{html.escape(alt)}">'
                f'<ri:attachment ri:filename="{html.escape(filename)}"/>'
                f"</ac:image></p>"
            )

    return f"<p>[image: {html.escape(alt or src)}]</p>"


def render_block_code(token, base_dir, **kwargs):
    """Render a code block as plain <pre><code> (upgraded to macro in task 4)."""
    raw = token.get("raw", "") or token.get("text", "")
    info = token.get("attrs", {}).get("info", "") if token.get("attrs") else ""
    lang = info.split()[0] if info else ""
    escaped = html.escape(raw)
    if lang:
        return f'<pre><code class="language-{html.escape(lang)}">{escaped}</code></pre>'
    return f"<pre><code>{escaped}</code></pre>"


def render_block_quote(token, base_dir, **kwargs):
    """Render a blockquote."""
    children = token.get("children", [])
    inner = "".join(render_block(c, base_dir, **kwargs) for c in children)
    return f"<blockquote>{inner}</blockquote>"


def render_alert(token, base_dir, **kwargs):
    """Render a GitHub-style alert as a blockquote (upgraded to macro in task 7)."""
    children = token.get("children", [])
    inner = "".join(render_block(c, base_dir, **kwargs) for c in children)
    return f"<blockquote>{inner}</blockquote>"


def render_list(token, base_dir, **kwargs):
    """Render ordered, unordered, and task lists."""
    attrs = token.get("attrs", {}) or {}
    ordered = attrs.get("ordered", False)
    tag = "ol" if ordered else "ul"
    items = []
    for item in token.get("children", []):
        item_children = item.get("children", [])
        is_task = item.get("type") == "task_list_item"
        checked = (
            item.get("attrs", {}).get("checked", False) if item.get("attrs") else False
        )
        parts = []
        for j, child in enumerate(item_children):
            if child["type"] in ("paragraph", "block_text"):
                prefix = ""
                if is_task and j == 0:
                    prefix = "\u2611 " if checked else "\u2610 "
                inner = render_inline(child.get("children", []), base_dir, **kwargs)
                parts.append(f"<p>{html.escape(prefix)}{inner}</p>")
            elif child["type"] == "list":
                parts.append(render_list(child, base_dir, **kwargs))
            else:
                parts.append(render_block(child, base_dir, **kwargs))
        items.append(f"<li>{''.join(parts)}</li>")
    return f"<{tag}>{''.join(items)}</{tag}>"


def render_table(token, base_dir, **kwargs):
    """Render a table (implemented in task 3; stub returns empty string)."""
    return ""


def render_thematic_break(token, base_dir, **kwargs):
    """Render a horizontal rule."""
    return "<hr />"


def render_inline(children, base_dir, **kwargs):
    """Recursive inline renderer for text, formatting, links, images, breaks."""
    if not children:
        return ""
    parts = []
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
            parts.append(html.escape(raw))

        elif t == "strong":
            inner = render_inline(child.get("children", []), base_dir, **kwargs)
            parts.append(f"<strong>{inner}</strong>")

        elif t == "emphasis":
            inner = render_inline(child.get("children", []), base_dir, **kwargs)
            parts.append(f"<em>{inner}</em>")

        elif t == "strikethrough":
            inner = render_inline(child.get("children", []), base_dir, **kwargs)
            parts.append(f"<del>{inner}</del>")

        elif t == "codespan":
            raw = child.get("raw", "") or child.get("text", "")
            if isinstance(raw, list):
                raw = extract_text(raw)
            parts.append(f"<code>{html.escape(raw)}</code>")

        elif t == "link":
            attrs = child.get("attrs", {}) or {}
            url = attrs.get("url", "") or attrs.get("href", "")
            link_text = render_inline(child.get("children", []), base_dir, **kwargs)
            if url:
                parts.append(f'<a href="{html.escape(url)}">{link_text}</a>')

        elif t == "image":
            # Inline image (inside paragraph with other content)
            src = child.get("attrs", {}).get("src", "")
            alt = child.get("attrs", {}).get("alt", "")
            client = kwargs.get("client")
            page_id = kwargs.get("page_id")
            uploaded = kwargs.get("uploaded")
            if client and page_id and src:
                img_path = resolve_image_path(src, base_dir)
                if img_path.exists():
                    filename = client.ensure_attachment(
                        page_id, str(img_path), uploaded
                    )
                    parts.append(
                        f'<ac:image ac:alt="{html.escape(alt)}">'
                        f'<ri:attachment ri:filename="{html.escape(filename)}"/>'
                        f"</ac:image>"
                    )
                    continue
            parts.append(f"[image: {html.escape(alt or src)}]")

        elif t == "softbreak":
            parts.append(" ")

        elif t == "linebreak":
            parts.append("<br />")

    return "".join(parts)


# ---------------------------------------------------------------------------
# Title extraction
# ---------------------------------------------------------------------------


def extract_title(tokens, fallback):
    """Return the text of the first h1 in the token list, or fallback."""
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
    """Parse MD, render to storage format, then create or update a Confluence page."""
    input_path = Path(input_path)
    md_text = input_path.read_text(encoding="utf-8")
    base_dir = str(input_path.parent)

    md = create_parser()
    tokens = md(md_text)
    tokens = preprocess_mermaid(tokens, base_dir)
    tokens = preprocess_alerts(tokens)
    tokens = preprocess_images(tokens)

    # Determine target page ID for attachment uploads
    target_page_id = page_id

    if page_id:
        page = client.get_page(page_id)
        title = page["title"]
        version = page["version"]["number"]
        # Fetch existing attachments once to avoid repeated API calls
        existing_attachments = client.get_attachments(page_id)
        body = render_tokens(
            tokens,
            base_dir,
            client=client,
            page_id=target_page_id,
            uploaded=existing_attachments,
        )
        click.echo(
            "Warning: updating this page will resolve any inline comments "
            "whose anchored text no longer exists in the new content.",
            err=True,
        )
        result = client.update_page(page_id, version, title, body)
    else:
        title = extract_title(tokens, input_path.stem)
        # Create page first (empty body) to get the page ID for attachments
        result = client.create_page(parent_id, space_key, title, "")
        target_page_id = result["id"]
        body = render_tokens(
            tokens,
            base_dir,
            client=client,
            page_id=target_page_id,
            uploaded={},
        )
        # Update with the rendered body
        result = client.update_page(
            target_page_id, result["version"]["number"], title, body
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
