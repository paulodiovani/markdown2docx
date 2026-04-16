"""Unit tests for lib.parser."""

from pathlib import Path

import pytest

from lib.parser import (
    CONTAINER_TYPES,
    build_heading_anchor_map,
    confluence_heading_anchor,
    create_parser,
    extract_text,
    heading_slug,
    preprocess_images,
    preprocess_tables_in_lists,
    resolve_image_path,
    walk_block_containers,
)


# ---------------------------------------------------------------------------
# extract_text
# ---------------------------------------------------------------------------


def test_extract_text_none_returns_empty():
    assert extract_text(None) == ""


def test_extract_text_empty_list():
    assert extract_text([]) == ""


def test_extract_text_raw_field():
    assert extract_text([{"raw": "hello"}]) == "hello"


def test_extract_text_text_field_fallback():
    assert extract_text([{"text": "world"}]) == "world"


def test_extract_text_raw_wins_over_text():
    assert extract_text([{"raw": "hello", "text": "world"}]) == "hello"


def test_extract_text_recurses_into_nested_children():
    children = [{"children": [{"raw": "foo "}, {"raw": "bar"}]}]
    assert extract_text(children) == "foo bar"


def test_extract_text_mixed_structure():
    children = [
        {"raw": "A"},
        {"text": "B"},
        {"children": [{"raw": "C"}, {"text": "D"}]},
    ]
    assert extract_text(children) == "ABCD"


# ---------------------------------------------------------------------------
# heading_slug
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Hello World", "hello-world"),
        ("Simple", "simple"),
        ("With, Punctuation!", "with-punctuation"),
        ("Keep-Hyphens", "keep-hyphens"),
        ("2.2 Non-Goals", "22-non-goals"),
        ("", ""),
    ],
)
def test_heading_slug(text, expected):
    assert heading_slug(text) == expected


def test_heading_slug_does_not_collapse_whitespace_runs():
    # \s is used (not \s+), so each whitespace char becomes its own hyphen.
    assert heading_slug("a  b") == "a--b"


# ---------------------------------------------------------------------------
# confluence_heading_anchor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Hello World", "Hello-World"),
        ("  Leading and Trailing  ", "Leading-and-Trailing"),
        ("Multiple   Spaces", "Multiple-Spaces"),
        ("PreserveCase", "PreserveCase"),
        ("Tab\tSeparated", "Tab-Separated"),
    ],
)
def test_confluence_heading_anchor(text, expected):
    assert confluence_heading_anchor(text) == expected


# ---------------------------------------------------------------------------
# build_heading_anchor_map
# ---------------------------------------------------------------------------


def test_build_heading_anchor_map_empty_tokens():
    assert build_heading_anchor_map([]) == {}


def test_build_heading_anchor_map_ignores_non_headings():
    tokens = [
        {"type": "paragraph", "children": [{"raw": "Not a heading"}]},
        {"type": "block_code", "raw": "code"},
    ]
    assert build_heading_anchor_map(tokens) == {}


def test_build_heading_anchor_map_maps_slug_to_anchor():
    tokens = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "children": [{"raw": "Hello World"}],
        },
        {
            "type": "heading",
            "attrs": {"level": 2},
            "children": [{"raw": "Section Two"}],
        },
    ]
    assert build_heading_anchor_map(tokens) == {
        "hello-world": "Hello-World",
        "section-two": "Section-Two",
    }


# ---------------------------------------------------------------------------
# resolve_image_path
# ---------------------------------------------------------------------------


def test_resolve_image_path_relative(tmp_path):
    assert resolve_image_path("sub/image.png", tmp_path) == tmp_path / "sub/image.png"


def test_resolve_image_path_absolute(tmp_path):
    abs_path = tmp_path / "absolute.png"
    assert resolve_image_path(str(abs_path), "/unused") == Path(str(abs_path))


def test_resolve_image_path_returns_path_object():
    assert isinstance(resolve_image_path("x.png", "."), Path)


# ---------------------------------------------------------------------------
# create_parser
# ---------------------------------------------------------------------------


def test_create_parser_returns_callable():
    assert callable(create_parser())


def test_create_parser_ast_mode():
    parser = create_parser()
    tokens = parser("# Heading\n\nParagraph text.\n")
    assert isinstance(tokens, list)
    assert tokens[0]["type"] == "heading"


def test_create_parser_enables_table_plugin():
    parser = create_parser()
    tokens = parser("| a | b |\n| - | - |\n| 1 | 2 |\n")
    assert any(t["type"] == "table" for t in tokens)


def test_create_parser_enables_strikethrough_plugin():
    parser = create_parser()
    tokens = parser("~~struck~~\n")

    def has_strike(nodes):
        for n in nodes:
            if n.get("type") == "strikethrough":
                return True
            if has_strike(n.get("children") or []):
                return True
        return False

    assert has_strike(tokens)


def test_create_parser_enables_task_lists_plugin():
    parser = create_parser()
    tokens = parser("- [ ] Todo\n- [x] Done\n")
    list_token = next(t for t in tokens if t["type"] == "list")
    item_types = [c["type"] for c in list_token["children"]]
    assert "task_list_item" in item_types


# ---------------------------------------------------------------------------
# walk_block_containers
# ---------------------------------------------------------------------------


def test_walk_block_containers_container_types_are_exactly_four():
    assert set(CONTAINER_TYPES) == {"list", "list_item", "block_quote", "alert"}


def test_walk_block_containers_calls_visit_on_top_level():
    calls = []

    def visit(tokens):
        calls.append([t.get("type") for t in tokens])
        return tokens

    walk_block_containers([{"type": "paragraph"}], visit)
    assert calls == [["paragraph"]]


def test_walk_block_containers_recurses_into_container_types():
    calls = []

    def visit(tokens):
        calls.append([t.get("type") for t in tokens])
        return tokens

    tokens = [
        {
            "type": "list",
            "children": [{"type": "list_item", "children": [{"type": "paragraph"}]}],
        }
    ]
    walk_block_containers(tokens, visit)
    assert calls == [["list"], ["list_item"], ["paragraph"]]


def test_walk_block_containers_does_not_recurse_into_non_containers():
    calls = []

    def visit(tokens):
        calls.append([t.get("type") for t in tokens])
        return tokens

    tokens = [
        {
            "type": "paragraph",
            "children": [{"type": "text", "raw": "x"}],
        },
        {"type": "heading", "children": [{"type": "text", "raw": "y"}]},
    ]
    walk_block_containers(tokens, visit)
    # Only one call: the top-level list. Paragraph/heading children aren't visited.
    assert calls == [["paragraph", "heading"]]


def test_walk_block_containers_visit_return_replaces_list():
    def visit(tokens):
        return [t for t in tokens if t.get("type") != "drop"]

    result = walk_block_containers(
        [{"type": "paragraph"}, {"type": "drop"}, {"type": "paragraph"}],
        visit,
    )
    assert [t["type"] for t in result] == ["paragraph", "paragraph"]


def test_walk_block_containers_visit_return_used_for_recursion():
    # If visit replaces a list_item with new container tokens, those are descended into.
    seen = []

    def visit(tokens):
        seen.append([t.get("type") for t in tokens])
        return tokens

    tokens = [
        {
            "type": "block_quote",
            "children": [{"type": "paragraph"}],
        }
    ]
    walk_block_containers(tokens, visit)
    assert seen == [["block_quote"], ["paragraph"]]


# ---------------------------------------------------------------------------
# preprocess_images
# ---------------------------------------------------------------------------


def test_preprocess_images_renames_url_to_src():
    tokens = [
        {
            "type": "paragraph",
            "children": [{"type": "image", "attrs": {"url": "pic.png"}}],
        }
    ]
    preprocess_images(tokens)
    assert tokens[0]["children"][0]["attrs"] == {"src": "pic.png"}


def test_preprocess_images_leaves_src_attr_alone():
    tokens = [
        {
            "type": "paragraph",
            "children": [{"type": "image", "attrs": {"src": "already.png"}}],
        }
    ]
    preprocess_images(tokens)
    assert tokens[0]["children"][0]["attrs"] == {"src": "already.png"}


def test_preprocess_images_ignores_non_image_children():
    tokens = [
        {
            "type": "paragraph",
            "children": [{"type": "text", "raw": "hello"}],
        }
    ]
    preprocess_images(tokens)
    assert tokens[0]["children"] == [{"type": "text", "raw": "hello"}]


def test_preprocess_images_recurses_into_containers():
    tokens = [
        {
            "type": "list",
            "children": [
                {
                    "type": "list_item",
                    "children": [
                        {
                            "type": "paragraph",
                            "children": [
                                {"type": "image", "attrs": {"url": "inside.png"}}
                            ],
                        }
                    ],
                }
            ],
        }
    ]
    preprocess_images(tokens)
    image = tokens[0]["children"][0]["children"][0]["children"][0]
    assert image["attrs"] == {"src": "inside.png"}


# ---------------------------------------------------------------------------
# preprocess_tables_in_lists
# ---------------------------------------------------------------------------


def _list_with_tabletext():
    """A token tree mimicking mistune's output for a table inside a list item.

    Mistune's GFM table plugin doesn't run inside list items, so the table
    lines come through as a paragraph of softbreak-separated text.
    """
    return [
        {
            "type": "list",
            "bullet": "-",
            "attrs": {"depth": 0, "ordered": False},
            "children": [
                {
                    "type": "list_item",
                    "children": [
                        {
                            "type": "paragraph",
                            "children": [
                                {"type": "text", "raw": "| a | b |"},
                                {"type": "softbreak"},
                                {"type": "text", "raw": "| - | - |"},
                                {"type": "softbreak"},
                                {"type": "text", "raw": "| 1 | 2 |"},
                            ],
                        }
                    ],
                }
            ],
        }
    ]


def test_preprocess_tables_in_lists_reparses_table():
    tokens = _list_with_tabletext()
    preprocess_tables_in_lists(tokens)
    child_types = [c["type"] for c in tokens[0]["children"][0]["children"]]
    assert "table" in child_types
    assert "paragraph" not in child_types


def test_preprocess_tables_in_lists_leaves_top_level_tables_untouched():
    parser = create_parser()
    tokens = parser("| a | b |\n| - | - |\n| 1 | 2 |\n")
    before = [t["type"] for t in tokens]
    preprocess_tables_in_lists(tokens)
    after = [t["type"] for t in tokens]
    assert before == after
    assert "table" in after


def test_preprocess_tables_in_lists_leaves_plain_paragraphs_untouched():
    tokens = [
        {
            "type": "list",
            "children": [
                {
                    "type": "list_item",
                    "children": [
                        {
                            "type": "paragraph",
                            "children": [{"type": "text", "raw": "Plain item text"}],
                        }
                    ],
                }
            ],
        }
    ]
    preprocess_tables_in_lists(tokens)
    child_types = [c["type"] for c in tokens[0]["children"][0]["children"]]
    assert child_types == ["paragraph"]
