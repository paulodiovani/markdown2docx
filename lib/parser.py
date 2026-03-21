"""Shared Markdown parsing utilities."""

import os
import re
from pathlib import Path

import mistune


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


def preprocess_images(tokens):
    """Normalize image attrs: rename 'url' to 'src' so all images use the same key."""
    for token in tokens:
        children = token.get("children", [])
        if children:
            for child in children:
                if child.get("type") == "image":
                    attrs = child.get("attrs", {})
                    if attrs and "url" in attrs:
                        attrs["src"] = attrs.pop("url")
    return tokens
