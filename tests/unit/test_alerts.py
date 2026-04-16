"""Unit tests for lib.alerts."""

import pytest

from lib.alerts import ALERT_STYLES, detect_alert_type, preprocess_alerts


def _alert_blockquote(alert_type, body_text="Body text"):
    """Build a blockquote token that looks like a GitHub-style alert."""
    return {
        "type": "block_quote",
        "children": [
            {
                "type": "paragraph",
                "children": [
                    {"type": "text", "raw": "["},
                    {"type": "text", "raw": f"!{alert_type}]"},
                    {"type": "softbreak"},
                    {"type": "text", "raw": body_text},
                ],
            }
        ],
    }


# ---------------------------------------------------------------------------
# detect_alert_type
# ---------------------------------------------------------------------------


def test_detect_alert_type_no_children_key():
    assert detect_alert_type({"type": "block_quote"}) is None


def test_detect_alert_type_empty_children():
    assert detect_alert_type({"type": "block_quote", "children": []}) is None


def test_detect_alert_type_first_child_not_paragraph():
    token = {
        "type": "block_quote",
        "children": [{"type": "block_code", "raw": "code"}],
    }
    assert detect_alert_type(token) is None


def test_detect_alert_type_fewer_than_two_inlines():
    token = {
        "type": "block_quote",
        "children": [{"type": "paragraph", "children": [{"type": "text", "raw": "["}]}],
    }
    assert detect_alert_type(token) is None


def test_detect_alert_type_first_inline_not_open_bracket():
    token = {
        "type": "block_quote",
        "children": [
            {
                "type": "paragraph",
                "children": [
                    {"type": "text", "raw": "("},
                    {"type": "text", "raw": "!NOTE]"},
                ],
            }
        ],
    }
    assert detect_alert_type(token) is None


def test_detect_alert_type_second_inline_wrong_shape():
    token = {
        "type": "block_quote",
        "children": [
            {
                "type": "paragraph",
                "children": [
                    {"type": "text", "raw": "["},
                    {"type": "text", "raw": "NOTE"},  # no ! prefix, no ] suffix
                ],
            }
        ],
    }
    assert detect_alert_type(token) is None


def test_detect_alert_type_unknown_alert_name():
    assert detect_alert_type(_alert_blockquote("UNKNOWN")) is None


@pytest.mark.parametrize("alert_type", sorted(ALERT_STYLES.keys()))
def test_detect_alert_type_recognizes_all_known_types(alert_type):
    assert detect_alert_type(_alert_blockquote(alert_type)) == alert_type


def test_detect_alert_type_lowercased_input_is_uppercased():
    assert detect_alert_type(_alert_blockquote("note")) == "NOTE"


def test_detect_alert_type_falls_back_to_text_field():
    token = {
        "type": "block_quote",
        "children": [
            {
                "type": "paragraph",
                "children": [
                    {"type": "text", "text": "["},
                    {"type": "text", "text": "!WARNING]"},
                ],
            }
        ],
    }
    assert detect_alert_type(token) == "WARNING"


# ---------------------------------------------------------------------------
# preprocess_alerts
# ---------------------------------------------------------------------------


def test_preprocess_alerts_rewrites_blockquote_to_alert_token():
    result = preprocess_alerts([_alert_blockquote("NOTE")])
    assert result[0]["type"] == "alert"
    assert result[0]["attrs"]["alert_type"] == "NOTE"


def test_preprocess_alerts_strips_marker_and_softbreak():
    result = preprocess_alerts([_alert_blockquote("TIP", body_text="Hello")])
    body = result[0]["children"]
    assert body[0]["type"] == "paragraph"
    inline_raws = [c.get("raw") for c in body[0]["children"]]
    assert inline_raws == ["Hello"]


def test_preprocess_alerts_handles_marker_only_paragraph():
    token = {
        "type": "block_quote",
        "children": [
            {
                "type": "paragraph",
                "children": [
                    {"type": "text", "raw": "["},
                    {"type": "text", "raw": "!NOTE]"},
                ],
            },
            {
                "type": "paragraph",
                "children": [{"type": "text", "raw": "Second para"}],
            },
        ],
    }
    result = preprocess_alerts([token])
    child_types = [c["type"] for c in result[0]["children"]]
    assert child_types == ["paragraph"]
    assert result[0]["children"][0]["children"][0]["raw"] == "Second para"


def test_preprocess_alerts_skips_blank_lines_in_body():
    token = {
        "type": "block_quote",
        "children": [
            {
                "type": "paragraph",
                "children": [
                    {"type": "text", "raw": "["},
                    {"type": "text", "raw": "!CAUTION]"},
                ],
            },
            {"type": "blank_line"},
            {
                "type": "paragraph",
                "children": [{"type": "text", "raw": "Body"}],
            },
        ],
    }
    result = preprocess_alerts([token])
    body_types = [c["type"] for c in result[0]["children"]]
    assert "blank_line" not in body_types


def test_preprocess_alerts_leaves_non_alert_blockquotes_alone():
    token = {
        "type": "block_quote",
        "children": [
            {
                "type": "paragraph",
                "children": [{"type": "text", "raw": "Plain quote"}],
            }
        ],
    }
    result = preprocess_alerts([token])
    assert result[0]["type"] == "block_quote"
    assert result[0] is token


def test_preprocess_alerts_recurses_into_list_items():
    tokens = [
        {
            "type": "list",
            "children": [
                {
                    "type": "list_item",
                    "children": [_alert_blockquote("WARNING")],
                }
            ],
        }
    ]
    preprocess_alerts(tokens)
    inner = tokens[0]["children"][0]["children"][0]
    assert inner["type"] == "alert"
    assert inner["attrs"]["alert_type"] == "WARNING"


def test_alert_styles_has_all_five_types():
    assert set(ALERT_STYLES.keys()) == {
        "NOTE",
        "TIP",
        "IMPORTANT",
        "WARNING",
        "CAUTION",
    }
