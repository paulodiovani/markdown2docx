"""Shared Markdown parsing utilities."""

import os
import re
from pathlib import Path

import mistune


# Block tokens whose children are themselves block tokens (not inlines).
# Used by walk_block_containers to recurse when preprocessing.
CONTAINER_TYPES = ("list", "list_item", "block_quote", "alert")


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


def heading_slug(text):
    """Convert heading text to a URL-compatible slug (GitHub anchor convention)."""
    slug = text.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"\s", "-", slug)
    return slug


def confluence_heading_anchor(text):
    """Convert heading text to Confluence's anchor format."""
    return re.sub(r"\s+", "-", text.strip())


def build_heading_anchor_map(tokens):
    """Build a mapping from GitHub-style slugs to Confluence-style anchors."""
    anchor_map = {}
    for token in tokens:
        if token.get("type") == "heading":
            text = extract_text(token.get("children", []))
            slug = heading_slug(text)
            anchor = confluence_heading_anchor(text)
            anchor_map[slug] = anchor
    return anchor_map


def resolve_image_path(url, base_dir):
    """Resolve image path relative to base_dir or as absolute."""
    if os.path.isabs(url):
        return Path(url)
    return Path(base_dir) / url


def create_parser():
    """Create and return a mistune Markdown parser with GFM plugins."""
    return mistune.create_markdown(
        renderer="ast",
        plugins=["table", "strikethrough", "task_lists"],
    )


def walk_block_containers(tokens, visit):
    """Apply visit(token_list) at every block-container level, depth-first.

    visit is called once per container token list (the top-level list, and
    the children list of every list/list_item/block_quote/alert). It must
    return a list of tokens that replaces the input list (may be the same
    list, mutated in place, or a new list).

    Descent happens AFTER visit runs on the enclosing list, so a visitor
    that replaces a token with new container tokens will have those new
    containers visited too.
    """
    tokens = visit(tokens)
    for token in tokens:
        if token.get("type") in CONTAINER_TYPES:
            children = token.get("children")
            if children:
                token["children"] = walk_block_containers(children, visit)
    return tokens


def preprocess_images(tokens):
    """Normalize image attrs: rename 'url' to 'src' so all images use the same key.

    Recurses into container tokens so images nested inside lists/blockquotes/
    alerts get normalized too.
    """

    def visit(token_list):
        for token in token_list:
            children = token.get("children")
            if not children:
                continue
            for child in children:
                if child.get("type") == "image":
                    attrs = child.get("attrs", {})
                    if attrs and "url" in attrs:
                        attrs["src"] = attrs.pop("url")
        return token_list

    return walk_block_containers(tokens, visit)


# ---------------------------------------------------------------------------
# Tables inside list items
# ---------------------------------------------------------------------------

# Mistune's GFM table plugin does not activate inside list items. When a GFM
# table appears as a block inside a list_item, mistune emits it as a plain
# paragraph whose inline children are text nodes separated by softbreaks.
# preprocess_tables_in_lists() detects that shape and re-parses the paragraph's
# text through mistune so the table plugin runs on it, then swaps in the
# resulting table token.

_TABLE_SEPARATOR_RE = re.compile(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")


def _paragraph_as_table_text(paragraph):
    """If a paragraph looks like a GFM table, return its reconstructed source.

    Returns None if the paragraph is not a table.
    """
    children = paragraph.get("children") or []
    if not children:
        return None

    lines = [""]
    for child in children:
        t = child.get("type")
        if t in ("text", "codespan"):
            lines[-1] += child.get("raw", "") or child.get("text", "")
        elif t in ("softbreak", "linebreak"):
            lines.append("")
        else:
            # Other inline types (emphasis, links, etc.) — reconstruct from raw
            raw = child.get("raw")
            if raw is not None:
                lines[-1] += raw
            else:
                return None

    if len(lines) < 2:
        return None

    stripped = [line.strip() for line in lines]
    if not all(line.startswith("|") and line.endswith("|") for line in stripped):
        return None
    if not _TABLE_SEPARATOR_RE.match(stripped[1]):
        return None

    return "\n".join(lines) + "\n"


def preprocess_tables_in_lists(tokens):
    """Detect GFM tables lost inside list items and re-parse them as tables.

    Mistune's GFM `table` plugin does not activate when parsing list item
    bodies, so `| a | b |` lines come through as a paragraph of softbreak-
    separated text. This pass detects that shape inside list_item children
    and re-parses the paragraph's raw text with mistune so the table plugin
    runs on it, replacing the paragraph with the resulting table token.
    """
    parser = create_parser()

    def visit(token_list):
        result = []
        for token in token_list:
            if token.get("type") == "list_item":
                new_children = []
                for child in token.get("children", []):
                    if child.get("type") == "paragraph":
                        src = _paragraph_as_table_text(child)
                        if src:
                            reparsed = parser(src)
                            new_children.extend(reparsed)
                            continue
                    new_children.append(child)
                token["children"] = new_children
            result.append(token)
        return result

    return walk_block_containers(tokens, visit)
