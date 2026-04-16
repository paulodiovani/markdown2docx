"""Unit tests for markdown2confluence.py (ADF renderers + comment re-anchoring)."""

import json

import markdown2confluence as m2c
from markdown2confluence import (
    _ALERT_TO_PANEL,
    _add_mark,
    _apply_expanding_search,
    _apply_mark_at,
    _build_global_text_map,
    _collect_annotated_texts,
    _context_matches,
    _extract_annotations_from_adf,
    _extract_comment_text,
    _mark,
    _media_single,
    _render_image_block,
    _text,
    _truncate,
    extract_title,
    reapply_comment_marks,
    render_alert,
    render_block_code,
    render_block_quote,
    render_heading,
    render_inline,
    render_list,
    render_paragraph,
    render_table,
    render_thematic_break,
    render_to_adf,
)


# ---------------------------------------------------------------------------
# ADF helpers
# ---------------------------------------------------------------------------


def test_text_builds_plain_text_node():
    assert _text("hi") == {"type": "text", "text": "hi"}


def test_text_with_marks_includes_marks_list():
    mark = {"type": "strong"}
    assert _text("hi", mark) == {
        "type": "text",
        "text": "hi",
        "marks": [mark],
    }


def test_mark_without_attrs():
    assert _mark("strong") == {"type": "strong"}


def test_mark_with_attrs():
    assert _mark("link", href="https://x") == {
        "type": "link",
        "attrs": {"href": "https://x"},
    }


def test_add_mark_appends_to_text_nodes():
    nodes = [{"type": "text", "text": "a"}]
    mark = {"type": "em"}
    out = _add_mark(nodes, mark)
    assert out[0]["marks"] == [mark]
    # Original nodes are not mutated
    assert "marks" not in nodes[0]


def test_add_mark_preserves_existing_marks():
    nodes = [{"type": "text", "text": "a", "marks": [{"type": "strong"}]}]
    out = _add_mark(nodes, {"type": "em"})
    assert out[0]["marks"] == [{"type": "strong"}, {"type": "em"}]


def test_add_mark_skips_non_text_nodes():
    nodes = [{"type": "mediaSingle", "attrs": {}}]
    out = _add_mark(nodes, {"type": "em"})
    assert out == nodes


# ---------------------------------------------------------------------------
# render_to_adf
# ---------------------------------------------------------------------------


def test_render_to_adf_wraps_in_doc_structure():
    result = render_to_adf([], "/tmp")
    assert result["type"] == "doc"
    assert result["version"] == 1
    assert result["content"] == []


def test_render_to_adf_dispatches_to_block_renderers():
    tokens = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "children": [{"type": "text", "raw": "Hi"}],
        }
    ]
    result = render_to_adf(tokens, "/tmp")
    assert result["content"][0]["type"] == "heading"


# ---------------------------------------------------------------------------
# render_heading
# ---------------------------------------------------------------------------


def test_render_heading_emits_heading_node_with_level():
    token = {
        "type": "heading",
        "attrs": {"level": 3},
        "children": [{"type": "text", "raw": "Title"}],
    }
    [node] = render_heading(token, "/tmp")
    assert node["type"] == "heading"
    assert node["attrs"] == {"level": 3}
    assert node["content"] == [{"type": "text", "text": "Title"}]


def test_render_heading_defaults_to_level_1():
    token = {"type": "heading", "children": [{"type": "text", "raw": "x"}]}
    [node] = render_heading(token, "/tmp")
    assert node["attrs"] == {"level": 1}


# ---------------------------------------------------------------------------
# render_paragraph
# ---------------------------------------------------------------------------


def test_render_paragraph_wraps_inline_content():
    token = {
        "type": "paragraph",
        "children": [{"type": "text", "raw": "Hi"}],
    }
    [node] = render_paragraph(token, "/tmp")
    assert node == {
        "type": "paragraph",
        "content": [{"type": "text", "text": "Hi"}],
    }


def test_render_paragraph_empty_content_returns_empty_list():
    token = {"type": "paragraph", "children": []}
    assert render_paragraph(token, "/tmp") == []


def test_render_paragraph_image_only_delegates_to_image_block():
    token = {
        "type": "paragraph",
        "children": [{"type": "image", "attrs": {"src": "x.png", "alt": "cat"}}],
    }
    # No client -> returns placeholder paragraph
    result = render_paragraph(token, "/tmp")
    assert result == [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": "[image: cat]"}],
        }
    ]


# ---------------------------------------------------------------------------
# _render_image_block / _media_single
# ---------------------------------------------------------------------------


def test_render_image_block_empty_src_returns_empty():
    token = {"type": "image", "attrs": {"src": ""}}
    assert _render_image_block(token, "/tmp") == []


def test_render_image_block_no_client_returns_placeholder():
    token = {"type": "image", "attrs": {"src": "x.png", "alt": "cat"}}
    result = _render_image_block(token, "/tmp")
    assert result[0]["type"] == "paragraph"
    assert result[0]["content"][0]["text"] == "[image: cat]"


def test_render_image_block_alt_falls_back_to_src():
    token = {"type": "image", "attrs": {"src": "x.png"}}
    result = _render_image_block(token, "/tmp")
    assert result[0]["content"][0]["text"] == "[image: x.png]"


def test_render_image_block_with_client_uploads_and_returns_mediasingle(
    small_jpeg, tmp_path
):
    class FakeClient:
        def ensure_attachment(self, page_id, path, uploaded):
            return {"media_id": "M1", "collection": "C1", "filename": "cat.jpg"}

    token = {"type": "image", "attrs": {"src": small_jpeg.name, "alt": "kitten"}}
    result = _render_image_block(
        token,
        str(small_jpeg.parent),
        client=FakeClient(),
        page_id="p1",
        uploaded={},
    )
    assert result[0]["type"] == "mediaSingle"
    assert result[0]["content"][0]["attrs"]["id"] == "M1"
    assert result[0]["content"][0]["attrs"]["collection"] == "C1"
    assert result[0]["content"][0]["attrs"]["alt"] == "kitten"


def test_render_image_block_missing_file_returns_placeholder(tmp_path):
    class FakeClient:
        def ensure_attachment(self, *a, **kw):  # pragma: no cover
            raise AssertionError("should not be called")

    token = {"type": "image", "attrs": {"src": "missing.png", "alt": "x"}}
    result = _render_image_block(
        token, str(tmp_path), client=FakeClient(), page_id="p", uploaded={}
    )
    assert result[0]["type"] == "paragraph"


def test_media_single_returns_none_when_media_id_missing():
    assert _media_single({"collection": "C"}) is None


def test_media_single_returns_none_when_collection_missing():
    assert _media_single({"media_id": "M"}) is None


def test_media_single_builds_full_structure():
    info = {"media_id": "M", "collection": "C"}
    node = _media_single(info, alt="hello")
    assert node["type"] == "mediaSingle"
    assert node["attrs"] == {
        "layout": "center",
        "width": 100,
        "widthType": "percentage",
    }
    assert node["content"][0]["attrs"] == {
        "id": "M",
        "type": "file",
        "collection": "C",
        "alt": "hello",
    }


# ---------------------------------------------------------------------------
# render_block_code
# ---------------------------------------------------------------------------


def test_render_block_code_includes_language_attr():
    token = {
        "type": "block_code",
        "raw": "print()",
        "attrs": {"info": "python"},
    }
    [node] = render_block_code(token, "/tmp")
    assert node["type"] == "codeBlock"
    assert node["attrs"] == {"language": "python"}
    assert node["content"] == [{"type": "text", "text": "print()"}]


def test_render_block_code_no_language_omits_attrs():
    token = {"type": "block_code", "raw": "plain", "attrs": {}}
    [node] = render_block_code(token, "/tmp")
    assert "attrs" not in node


def test_render_block_code_multiword_info_uses_first_token():
    token = {
        "type": "block_code",
        "raw": "x",
        "attrs": {"info": "python foo"},
    }
    [node] = render_block_code(token, "/tmp")
    assert node["attrs"] == {"language": "python"}


# ---------------------------------------------------------------------------
# render_block_quote
# ---------------------------------------------------------------------------


def test_render_block_quote_wraps_children_in_blockquote():
    token = {
        "type": "block_quote",
        "children": [
            {
                "type": "paragraph",
                "children": [{"type": "text", "raw": "quoted"}],
            }
        ],
    }
    [node] = render_block_quote(token, "/tmp")
    assert node["type"] == "blockquote"
    assert node["content"][0]["type"] == "paragraph"


# ---------------------------------------------------------------------------
# render_alert
# ---------------------------------------------------------------------------


def test_render_alert_maps_type_to_panel_type():
    for alert_type, panel_type in _ALERT_TO_PANEL.items():
        token = {
            "type": "alert",
            "attrs": {"alert_type": alert_type},
            "children": [
                {"type": "paragraph", "children": [{"type": "text", "raw": "x"}]}
            ],
        }
        [node] = render_alert(token, "/tmp")
        assert node["type"] == "panel"
        assert node["attrs"] == {"panelType": panel_type}


def test_render_alert_empty_children_fills_empty_paragraph():
    token = {"type": "alert", "attrs": {"alert_type": "NOTE"}, "children": []}
    [node] = render_alert(token, "/tmp")
    assert node["content"][0]["type"] == "paragraph"


def test_render_alert_unknown_type_defaults_to_info():
    token = {
        "type": "alert",
        "attrs": {"alert_type": "XYZ"},
        "children": [{"type": "paragraph", "children": [{"type": "text", "raw": "x"}]}],
    }
    [node] = render_alert(token, "/tmp")
    assert node["attrs"] == {"panelType": "info"}


# ---------------------------------------------------------------------------
# render_list
# ---------------------------------------------------------------------------


def _simple_list_item(text, item_type="list_item"):
    return {
        "type": item_type,
        "children": [
            {
                "type": "block_text",
                "children": [{"type": "text", "raw": text}],
            }
        ],
    }


def test_render_list_unordered_emits_bullet_list():
    token = {
        "type": "list",
        "attrs": {"ordered": False},
        "children": [_simple_list_item("a")],
    }
    [node] = render_list(token, "/tmp")
    assert node["type"] == "bulletList"
    assert node["content"][0]["type"] == "listItem"


def test_render_list_ordered_emits_ordered_list_with_order_1():
    token = {
        "type": "list",
        "attrs": {"ordered": True},
        "children": [_simple_list_item("a"), _simple_list_item("b")],
    }
    [node] = render_list(token, "/tmp")
    assert node["type"] == "orderedList"
    assert node["attrs"] == {"order": 1}
    assert len(node["content"]) == 2


def test_render_list_task_item_prefixes_checkbox():
    token = {
        "type": "list",
        "attrs": {"ordered": False},
        "children": [
            {
                "type": "task_list_item",
                "attrs": {"checked": True},
                "children": [
                    {
                        "type": "block_text",
                        "children": [{"type": "text", "raw": "done"}],
                    }
                ],
            }
        ],
    }
    [node] = render_list(token, "/tmp")
    para_content = node["content"][0]["content"][0]["content"]
    assert para_content[0]["text"] == "\u2611 "


def test_render_list_splits_around_disallowed_block():
    """When a list item contains a table (not ADF-listItem-allowed), the list
    splits: items before flush as one list, the table emits at doc level,
    and remaining items resume in a fresh segment.
    """
    table_child = {
        "type": "table",
        "children": [
            {
                "type": "table_head",
                "children": [
                    {
                        "type": "table_cell",
                        "children": [{"type": "text", "raw": "A"}],
                    }
                ],
            }
        ],
    }
    token = {
        "type": "list",
        "attrs": {"ordered": True},
        "children": [
            {
                "type": "list_item",
                "children": [
                    {
                        "type": "block_text",
                        "children": [{"type": "text", "raw": "item1"}],
                    },
                    table_child,
                ],
            },
            _simple_list_item("item2"),
        ],
    }
    result = render_list(token, "/tmp")
    types = [n["type"] for n in result]
    assert "orderedList" in types
    assert "table" in types
    # Second list segment exists for item2
    ordered_segments = [n for n in result if n["type"] == "orderedList"]
    assert len(ordered_segments) == 2
    assert ordered_segments[1]["attrs"]["order"] == 2


# ---------------------------------------------------------------------------
# render_table
# ---------------------------------------------------------------------------


def _table_token():
    return {
        "type": "table",
        "children": [
            {
                "type": "table_head",
                "children": [
                    {
                        "type": "table_cell",
                        "attrs": {"align": "left"},
                        "children": [{"type": "text", "raw": "A"}],
                    },
                    {
                        "type": "table_cell",
                        "attrs": {"align": "right"},
                        "children": [{"type": "text", "raw": "B"}],
                    },
                ],
            },
            {
                "type": "table_body",
                "children": [
                    {
                        "type": "table_row",
                        "children": [
                            {
                                "type": "table_cell",
                                "children": [{"type": "text", "raw": "1"}],
                            },
                            {
                                "type": "table_cell",
                                "children": [{"type": "text", "raw": "2"}],
                            },
                        ],
                    }
                ],
            },
        ],
    }


def test_render_table_emits_table_with_rows():
    [node] = render_table(_table_token(), "/tmp")
    assert node["type"] == "table"
    assert len(node["content"]) == 2  # 1 header + 1 body row
    assert all(r["type"] == "tableRow" for r in node["content"])


def test_render_table_header_cells_use_tableheader_type():
    [node] = render_table(_table_token(), "/tmp")
    header_cells = node["content"][0]["content"]
    assert all(c["type"] == "tableHeader" for c in header_cells)


def test_render_table_body_cells_use_tablecell_type():
    [node] = render_table(_table_token(), "/tmp")
    body_cells = node["content"][1]["content"]
    assert all(c["type"] == "tableCell" for c in body_cells)


def test_render_table_applies_alignment_from_head():
    [node] = render_table(_table_token(), "/tmp")
    body_row = node["content"][1]["content"]
    # second col = "right"
    assert body_row[1]["content"][0]["attrs"] == {"alignment": "right"}


def test_render_table_empty_children_returns_empty():
    assert render_table({"type": "table", "children": []}, "/tmp") == []


# ---------------------------------------------------------------------------
# render_thematic_break
# ---------------------------------------------------------------------------


def test_render_thematic_break_emits_rule_node():
    assert render_thematic_break({"type": "thematic_break"}, "/tmp") == [
        {"type": "rule"}
    ]


# ---------------------------------------------------------------------------
# render_inline
# ---------------------------------------------------------------------------


def test_render_inline_empty_returns_empty():
    assert render_inline([], "/tmp") == []
    assert render_inline(None, "/tmp") == []


def test_render_inline_text_emits_text_node():
    children = [{"type": "text", "raw": "hi"}]
    assert render_inline(children, "/tmp") == [{"type": "text", "text": "hi"}]


def test_render_inline_strong_adds_mark():
    children = [{"type": "strong", "children": [{"type": "text", "raw": "bold"}]}]
    result = render_inline(children, "/tmp")
    assert result[0]["marks"] == [{"type": "strong"}]


def test_render_inline_emphasis_adds_em_mark():
    children = [{"type": "emphasis", "children": [{"type": "text", "raw": "em"}]}]
    assert render_inline(children, "/tmp")[0]["marks"] == [{"type": "em"}]


def test_render_inline_strikethrough_adds_strike_mark():
    children = [{"type": "strikethrough", "children": [{"type": "text", "raw": "x"}]}]
    assert render_inline(children, "/tmp")[0]["marks"] == [{"type": "strike"}]


def test_render_inline_codespan_adds_code_mark():
    children = [{"type": "codespan", "raw": "x"}]
    assert render_inline(children, "/tmp") == [
        {"type": "text", "text": "x", "marks": [{"type": "code"}]}
    ]


def test_render_inline_external_link():
    children = [
        {
            "type": "link",
            "attrs": {"url": "https://example.com"},
            "children": [{"type": "text", "raw": "ex"}],
        }
    ]
    [node] = render_inline(children, "/tmp")
    assert node["marks"] == [{"type": "link", "attrs": {"href": "https://example.com"}}]


def test_render_inline_internal_link_uses_anchor_map():
    children = [
        {
            "type": "link",
            "attrs": {"url": "#foo"},
            "children": [{"type": "text", "raw": "go"}],
        }
    ]
    anchor_map = {"foo": "Foo-Heading"}
    [node] = render_inline(children, "/tmp", anchor_map=anchor_map)
    assert node["marks"] == [{"type": "link", "attrs": {"href": "#Foo-Heading"}}]


def test_render_inline_internal_link_falls_back_to_slug_when_no_map_entry():
    children = [
        {
            "type": "link",
            "attrs": {"url": "#unknown"},
            "children": [{"type": "text", "raw": "x"}],
        }
    ]
    [node] = render_inline(children, "/tmp", anchor_map={})
    assert node["marks"] == [{"type": "link", "attrs": {"href": "#unknown"}}]


def test_render_inline_softbreak_becomes_space():
    children = [{"type": "softbreak"}]
    assert render_inline(children, "/tmp") == [{"type": "text", "text": " "}]


def test_render_inline_linebreak_becomes_hardbreak():
    children = [{"type": "linebreak"}]
    assert render_inline(children, "/tmp") == [{"type": "hardBreak"}]


def test_render_inline_image_without_client_placeholder():
    children = [
        {
            "type": "image",
            "attrs": {"src": "x.png", "alt": "cat"},
        }
    ]
    result = render_inline(children, "/tmp")
    assert result == [{"type": "text", "text": "[image: cat]"}]


# ---------------------------------------------------------------------------
# extract_title
# ---------------------------------------------------------------------------


def test_extract_title_returns_first_h1():
    tokens = [
        {
            "type": "heading",
            "attrs": {"level": 2},
            "children": [{"type": "text", "raw": "H2"}],
        },
        {
            "type": "heading",
            "attrs": {"level": 1},
            "children": [{"type": "text", "raw": "H1 Title"}],
        },
    ]
    assert extract_title(tokens, "fallback") == "H1 Title"


def test_extract_title_falls_back_when_no_h1():
    tokens = [
        {
            "type": "heading",
            "attrs": {"level": 2},
            "children": [{"type": "text", "raw": "H2"}],
        }
    ]
    assert extract_title(tokens, "fallback") == "fallback"


def test_extract_title_empty_tokens():
    assert extract_title([], "fallback") == "fallback"


# ---------------------------------------------------------------------------
# Comment re-anchoring helpers
# ---------------------------------------------------------------------------


def test_truncate_short_text_unchanged():
    assert _truncate("hi") == "hi"


def test_truncate_long_text_adds_ellipsis():
    result = _truncate("x" * 100, max_len=10)
    assert result == "x" * 10 + "…"


def test_extract_comment_text_empty_body():
    assert _extract_comment_text({}) == ""


def test_extract_comment_text_invalid_json():
    comment = {
        "body": {"atlas_doc_format": {"value": "not-json{{{"}},
    }
    assert _extract_comment_text(comment) == ""


def test_extract_comment_text_walks_adf_tree():
    import json as _json

    adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Hello "},
                    {"type": "text", "text": "world"},
                ],
            }
        ],
    }
    comment = {"body": {"atlas_doc_format": {"value": _json.dumps(adf)}}}
    assert _extract_comment_text(comment) == "Hello world"


def test_collect_annotated_texts_finds_annotated_nodes():
    node = {
        "type": "paragraph",
        "content": [
            {
                "type": "text",
                "text": "marked",
                "marks": [{"type": "annotation", "attrs": {"id": "UUID-1"}}],
            },
            {"type": "text", "text": "plain"},
        ],
    }
    entries = []
    _collect_annotated_texts(node, block_idx=5, entries=entries)
    assert entries == [("UUID-1", 5, "marked")]


def test_extract_annotations_from_adf_groups_by_uuid():
    adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "Hello ",
                        "marks": [{"type": "annotation", "attrs": {"id": "U1"}}],
                    },
                    {
                        "type": "text",
                        "text": "world",
                        "marks": [{"type": "annotation", "attrs": {"id": "U1"}}],
                    },
                ],
            }
        ],
    }
    result = _extract_annotations_from_adf(adf)
    assert result["U1"]["selection"] == "Hello world"
    assert result["U1"]["anchor_block"] == 0


def test_extract_annotations_from_adf_no_annotations():
    adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "plain"}],
            }
        ],
    }
    assert _extract_annotations_from_adf(adf) == {}


def test_build_global_text_map_concatenates_block_texts():
    blocks = [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": "Hello "}],
        },
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": "world"}],
        },
    ]
    nodes, global_text = _build_global_text_map(blocks)
    assert global_text == "Hello world"
    assert len(nodes) == 2
    assert nodes[0][1] == 0  # block_idx for first
    assert nodes[1][1] == 1  # block_idx for second
    assert nodes[0][2:] == (0, 6)  # (start, end)


def test_context_matches_empty_context_returns_true():
    assert _context_matches("any", 0, "sel", ("", "")) is True


def test_context_matches_perfect_surrounding_match():
    global_text = "the cat sat"
    # selection "cat" at idx=4. prefix "the " suffix " sat"
    assert _context_matches(global_text, 4, "cat", ("the ", " sat")) is True


def test_context_matches_fails_on_divergent_context():
    global_text = "abc cat xyz"
    # expected prefix "dog " and suffix " foo" — neither matches
    assert _context_matches(global_text, 4, "cat", ("dog ", " foo")) is False


def test_apply_mark_at_adds_annotation_to_overlapping_nodes():
    text_node = {"type": "text", "text": "hello"}
    text_nodes = [(text_node, 0, 0, 5)]
    applied = set()
    matched = _apply_mark_at(text_nodes, "U1", 0, 5, applied)
    assert matched is True
    assert "U1" in applied
    assert text_node["marks"] == [
        {
            "type": "annotation",
            "attrs": {"annotationType": "inlineComment", "id": "U1"},
        }
    ]


def test_apply_mark_at_no_overlap_returns_false():
    text_node = {"type": "text", "text": "hello"}
    text_nodes = [(text_node, 0, 0, 5)]
    applied = set()
    matched = _apply_mark_at(text_nodes, "U1", 10, 15, applied)
    assert matched is False
    assert "U1" not in applied


def test_apply_expanding_search_finds_and_marks():
    text_node = {"type": "text", "text": "Hello world"}
    text_nodes = [(text_node, 0, 0, 11)]
    applied = set()
    result = _apply_expanding_search(
        text_nodes, "Hello world", "U1", "world", 0, applied
    )
    assert result["matched"] is True
    assert result["new_block"] == 0
    assert "U1" in applied


def test_apply_expanding_search_not_found_returns_false():
    text_node = {"type": "text", "text": "foo"}
    text_nodes = [(text_node, 0, 0, 3)]
    applied = set()
    result = _apply_expanding_search(text_nodes, "foo", "U1", "missing", 0, applied)
    assert result["matched"] is False


def test_apply_expanding_search_empty_text_nodes():
    result = _apply_expanding_search([], "", "U1", "x", 0, set())
    assert result["matched"] is False


# ---------------------------------------------------------------------------
# reapply_comment_marks  (integration of the above)
# ---------------------------------------------------------------------------


def test_reapply_comment_marks_transfers_annotation():
    """Annotation from old_adf is re-applied to matching text in new_adf."""
    old_adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "Hello world",
                        "marks": [{"type": "annotation", "attrs": {"id": "U1"}}],
                    }
                ],
            }
        ],
    }
    new_adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Hello world"}],
            }
        ],
    }
    result = reapply_comment_marks(new_adf, old_adf, comments=[])
    marks = result["content"][0]["content"][0].get("marks", [])
    assert any(
        m.get("type") == "annotation" and m["attrs"]["id"] == "U1" for m in marks
    )


def test_reapply_comment_marks_no_annotations_returns_new_adf_unchanged():
    old_adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "plain"}],
            }
        ],
    }
    new_adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "plain"}],
            }
        ],
    }
    result = reapply_comment_marks(new_adf, old_adf, comments=[])
    assert result is new_adf


def test_reapply_comment_marks_warns_on_already_dangling_comment(capsys):
    """An API comment whose UUID isn't in old ADF should be flagged as dangling."""
    old_adf = {"type": "doc", "content": []}
    new_adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "some body"}],
            }
        ],
    }
    comments = [
        {
            "properties": {
                "inlineMarkerRef": "U-DANGLING",
                "inlineOriginalSelection": "ghost text",
            },
            "body": {
                "atlas_doc_format": {
                    "value": json.dumps(
                        {
                            "type": "doc",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {"type": "text", "text": "body of comment"}
                                    ],
                                }
                            ],
                        }
                    )
                }
            },
        }
    ]
    reapply_comment_marks(new_adf, old_adf, comments=comments)
    err = capsys.readouterr().err
    assert "already" in err and "dangling" in err
    assert "body of comment" in err


def test_reapply_comment_marks_warns_when_text_not_found(capsys):
    """Comment whose selection isn't found in new ADF triggers a warning."""
    old_adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "VANISHED_STRING",
                        "marks": [
                            {
                                "type": "annotation",
                                "attrs": {
                                    "id": "U-GONE",
                                    "annotationType": "inlineComment",
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }
    new_adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "completely different text"}],
            }
        ],
    }
    comments = [
        {
            "properties": {
                "inlineMarkerRef": "U-GONE",
                "inlineOriginalSelection": "VANISHED_STRING",
            },
            "body": {
                "atlas_doc_format": {
                    "value": json.dumps({"type": "doc", "content": []})
                }
            },
        }
    ]
    reapply_comment_marks(new_adf, old_adf, comments=comments)
    err = capsys.readouterr().err
    assert "could not be" in err
    assert "VANISHED_STRING" in err


def test_reapply_comment_marks_skips_anchored_with_no_selection():
    """Annotation in old ADF with empty text is skipped without error."""
    old_adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "",
                        "marks": [
                            {
                                "type": "annotation",
                                "attrs": {
                                    "id": "U-EMPTY",
                                    "annotationType": "inlineComment",
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }
    new_adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "hello"}],
            }
        ],
    }
    result = reapply_comment_marks(new_adf, old_adf, comments=[])
    assert result is not None


def test_reapply_comment_marks_handles_shifted_block_position():
    """Annotation whose anchor block moved down 1 still gets re-applied."""
    old_adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "UNIQUE_TARGET_STR",
                        "marks": [{"type": "annotation", "attrs": {"id": "U1"}}],
                    }
                ],
            }
        ],
    }
    new_adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "an inserted block"}],
            },
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "UNIQUE_TARGET_STR"}],
            },
        ],
    }
    result = reapply_comment_marks(new_adf, old_adf, comments=[])
    target = result["content"][1]["content"][0]
    assert any(m["attrs"].get("id") == "U1" for m in target.get("marks", []))


# ---------------------------------------------------------------------------
# convert_file (thin integration — verifies orchestrator wiring)
# ---------------------------------------------------------------------------


class _StubClient:
    """Minimal fake client for testing convert_file without real HTTP."""

    def __init__(self):
        self.created = []
        self.updated = []

    def get_page(self, page_id):
        return {
            "id": page_id,
            "title": "Old Title",
            "version": {"number": 3},
            "body": {"atlas_doc_format": {"value": '{"type":"doc","content":[]}'}},
            "_links": {"base": "https://c.example", "webui": "/pages/1"},
        }

    def get_page_adf(self, page):
        import json as _json

        return _json.loads(page["body"]["atlas_doc_format"]["value"])

    def get_attachments(self, page_id):
        return {}

    def get_inline_comments(self, page_id):
        return []

    def create_page(self, parent_id, space_key, title, adf_doc=None):
        result = {
            "id": "NEW123",
            "title": title,
            "version": {"number": 1},
            "_links": {"base": "https://c.example", "webui": "/pages/NEW"},
        }
        self.created.append(
            {"parent_id": parent_id, "space_key": space_key, "title": title}
        )
        return result

    def update_page(self, page_id, current_version, title, adf_doc):
        self.updated.append(
            {"page_id": page_id, "version": current_version, "title": title}
        )
        return {
            "id": page_id,
            "title": title,
            "_links": {"base": "https://c.example", "webui": f"/pages/{page_id}"},
        }

    def page_url(self, page):
        links = page.get("_links", {})
        return f"{links.get('base', '')}{links.get('webui', '')}"


def test_convert_file_update_path_calls_get_and_update(tmp_path):
    md = tmp_path / "x.md"
    md.write_text("# Hello\n\nPara.\n")
    client = _StubClient()
    url = m2c.convert_file(str(md), client, page_id="P1")
    assert client.updated[0]["page_id"] == "P1"
    assert client.updated[0]["version"] == 3
    assert url == "https://c.example/pages/P1"


def test_convert_file_create_path_creates_then_updates(tmp_path):
    md = tmp_path / "x.md"
    md.write_text("# My Title\n\nBody.\n")
    client = _StubClient()
    m2c.convert_file(str(md), client, parent_id="PARENT", space_key="SP")
    assert client.created[0]["title"] == "My Title"
    # After create, we call update_page to set the body
    assert client.updated[0]["page_id"] == "NEW123"


def test_convert_file_dry_run_update_does_not_update(tmp_path):
    md = tmp_path / "x.md"
    md.write_text("# t\n")
    client = _StubClient()
    m2c.convert_file(str(md), client, page_id="P1", dry_run=True)
    assert client.updated == []


def test_convert_file_dry_run_create_returns_none(tmp_path):
    md = tmp_path / "x.md"
    md.write_text("# t\n")
    client = _StubClient()
    result = m2c.convert_file(
        str(md), client, parent_id="P", space_key="SP", dry_run=True
    )
    assert result is None
    assert client.created == []
