"""Unit tests for lib.mermaid."""

import pytest

from lib.mermaid import MERMAID_THEMES, preprocess_mermaid


@pytest.fixture
def fake_mmdc(tmp_path, monkeypatch):
    """Redirect ``TEMP_DIR`` to tmp_path and stub out ``subprocess.run``.

    Returns a list that records each captured invocation as
    ``{"cmd": [...], "kwargs": {...}}``.
    """
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, "kwargs": kwargs})

    monkeypatch.setattr("lib.mermaid.TEMP_DIR", tmp_path)
    monkeypatch.setattr("lib.mermaid.subprocess.run", fake_run)
    return calls


def _mermaid_block(raw="graph TD;A-->B"):
    return {"type": "block_code", "raw": raw, "attrs": {"info": "mermaid"}}


def test_mermaid_themes_expected_values():
    assert MERMAID_THEMES == ("default", "neutral", "dark", "forest")


def test_preprocess_mermaid_replaces_block_with_image_paragraph(fake_mmdc, tmp_path):
    tokens = [_mermaid_block()]
    result = preprocess_mermaid(tokens, tmp_path)
    assert len(result) == 1
    assert result[0]["type"] == "paragraph"
    image = result[0]["children"][0]
    assert image["type"] == "image"
    assert image["attrs"]["alt"] == "mermaid diagram"
    assert image["attrs"]["src"].endswith(".png")


def test_preprocess_mermaid_leaves_non_mermaid_code_blocks(fake_mmdc, tmp_path):
    tokens = [
        {"type": "block_code", "raw": "print('hi')", "attrs": {"info": "python"}},
    ]
    result = preprocess_mermaid(tokens, tmp_path)
    assert result == tokens
    assert fake_mmdc == []


def test_preprocess_mermaid_leaves_plain_code_blocks_with_no_info(fake_mmdc, tmp_path):
    tokens = [{"type": "block_code", "raw": "code", "attrs": {}}]
    result = preprocess_mermaid(tokens, tmp_path)
    assert result == tokens
    assert fake_mmdc == []


def test_preprocess_mermaid_invokes_mmdc_with_check_true(fake_mmdc, tmp_path):
    preprocess_mermaid([_mermaid_block()], tmp_path)
    assert len(fake_mmdc) == 1
    assert fake_mmdc[0]["cmd"][0] == "mmdc"
    assert fake_mmdc[0]["kwargs"]["check"] is True


def test_preprocess_mermaid_passes_input_and_output_paths(fake_mmdc, tmp_path):
    preprocess_mermaid([_mermaid_block()], tmp_path)
    cmd = fake_mmdc[0]["cmd"]
    assert "-i" in cmd
    assert "-o" in cmd
    in_path = cmd[cmd.index("-i") + 1]
    out_path = cmd[cmd.index("-o") + 1]
    assert in_path.endswith(".mmd")
    assert out_path.endswith(".png")


def test_preprocess_mermaid_passes_theme_flag(fake_mmdc, tmp_path):
    preprocess_mermaid([_mermaid_block()], tmp_path, theme="dark")
    cmd = fake_mmdc[0]["cmd"]
    assert "-t" in cmd
    assert cmd[cmd.index("-t") + 1] == "dark"


def test_preprocess_mermaid_omits_theme_flag_when_none(fake_mmdc, tmp_path):
    preprocess_mermaid([_mermaid_block()], tmp_path, theme=None)
    assert "-t" not in fake_mmdc[0]["cmd"]


def test_preprocess_mermaid_passes_transparent_bg_flag(fake_mmdc, tmp_path):
    preprocess_mermaid([_mermaid_block()], tmp_path, transparent_bg=True)
    cmd = fake_mmdc[0]["cmd"]
    assert "-b" in cmd
    assert cmd[cmd.index("-b") + 1] == "transparent"


def test_preprocess_mermaid_omits_transparent_bg_flag_when_false(fake_mmdc, tmp_path):
    preprocess_mermaid([_mermaid_block()], tmp_path, transparent_bg=False)
    assert "-b" not in fake_mmdc[0]["cmd"]


def test_preprocess_mermaid_counter_increments_across_blocks(fake_mmdc, tmp_path):
    tokens = [_mermaid_block("a"), _mermaid_block("b")]
    result = preprocess_mermaid(tokens, tmp_path)
    src_a = result[0]["children"][0]["attrs"]["src"]
    src_b = result[1]["children"][0]["attrs"]["src"]
    assert src_a != src_b
    assert "_0_" in src_a
    assert "_1_" in src_b


def test_preprocess_mermaid_recurses_into_list_items(fake_mmdc, tmp_path):
    tokens = [
        {
            "type": "list",
            "children": [
                {"type": "list_item", "children": [_mermaid_block()]},
            ],
        }
    ]
    preprocess_mermaid(tokens, tmp_path)
    assert len(fake_mmdc) == 1
    inner = tokens[0]["children"][0]["children"][0]
    assert inner["type"] == "paragraph"
    assert inner["children"][0]["type"] == "image"


def test_preprocess_mermaid_handles_multiword_info(fake_mmdc, tmp_path):
    # `info` sometimes contains a language and extras: "mermaid foo"
    tokens = [
        {"type": "block_code", "raw": "g", "attrs": {"info": "mermaid extra"}},
    ]
    result = preprocess_mermaid(tokens, tmp_path)
    assert result[0]["type"] == "paragraph"
    assert len(fake_mmdc) == 1


def test_preprocess_mermaid_writes_source_to_mmd_file(fake_mmdc, tmp_path):
    preprocess_mermaid([_mermaid_block("graph A-->B")], tmp_path)
    cmd = fake_mmdc[0]["cmd"]
    mmd_path = cmd[cmd.index("-i") + 1]
    from pathlib import Path

    assert Path(mmd_path).read_text() == "graph A-->B"
