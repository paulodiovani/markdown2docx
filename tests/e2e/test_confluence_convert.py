"""End-to-end tests for the Confluence conversion pipeline.

These tests run ``markdown2confluence.convert_file()`` against real files
in ``examples/`` with the Confluence HTTP API intercepted by ``responses``.
No real network traffic occurs.
"""

import json
from pathlib import Path

import pytest
import responses

import markdown2confluence as m2c
from lib.confluence import ConfluenceClient


EXAMPLES = Path(__file__).resolve().parent.parent.parent / "examples"
BASE_URL = "https://test.atlassian.net"


@pytest.fixture
def client(mock_confluence_config):
    """A real ConfluenceClient whose config comes from the test fixture."""
    return ConfluenceClient()


def _existing_page(page_id="P1", version=3, title="Old Title", adf=None):
    """Build a fake ``get_page`` response body."""
    if adf is None:
        adf = {"type": "doc", "version": 1, "content": []}
    return {
        "id": page_id,
        "title": title,
        "version": {"number": version},
        "body": {"atlas_doc_format": {"value": json.dumps(adf)}},
        "_links": {"base": BASE_URL, "webui": f"/wiki/spaces/X/pages/{page_id}"},
    }


def _updated_page(page_id="P1", version=4, title="Hello"):
    return {
        "id": page_id,
        "title": title,
        "version": {"number": version},
        "_links": {"base": BASE_URL, "webui": f"/wiki/spaces/X/pages/{page_id}"},
    }


def _register_noop_update(page_id="P1"):
    """Register GET page + GET attachments + GET inline comments + PUT update."""
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/rest/api/content/{page_id}",
        json=_existing_page(page_id=page_id),
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/rest/api/content/{page_id}/child/attachment",
        json={"results": []},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/api/v2/pages/{page_id}/inline-comments",
        json={"results": []},
        status=200,
    )
    responses.add(
        responses.PUT,
        f"{BASE_URL}/wiki/rest/api/content/{page_id}",
        json=_updated_page(page_id=page_id),
        status=200,
    )


# ---------------------------------------------------------------------------
# Update existing page flow
# ---------------------------------------------------------------------------


@responses.activate
def test_update_existing_page_sends_put_with_incremented_version(client):
    _register_noop_update()
    m2c.convert_file(str(EXAMPLES / "basic.md"), client, page_id="P1")

    put_calls = [c for c in responses.calls if c.request.method == "PUT"]
    assert len(put_calls) == 1
    body = json.loads(put_calls[0].request.body)
    assert body["version"]["number"] == 4  # was 3, now 4


@responses.activate
def test_update_existing_page_body_is_valid_adf(client):
    _register_noop_update()
    m2c.convert_file(str(EXAMPLES / "basic.md"), client, page_id="P1")

    put_body = json.loads(
        [c for c in responses.calls if c.request.method == "PUT"][0].request.body
    )
    adf = json.loads(put_body["body"]["atlas_doc_format"]["value"])
    assert adf["type"] == "doc"
    assert adf["version"] == 1
    assert adf["content"]


@responses.activate
def test_update_existing_page_adf_includes_heading(client):
    _register_noop_update()
    m2c.convert_file(str(EXAMPLES / "basic.md"), client, page_id="P1")

    put_body = json.loads(
        [c for c in responses.calls if c.request.method == "PUT"][0].request.body
    )
    adf = json.loads(put_body["body"]["atlas_doc_format"]["value"])
    top_types = [n["type"] for n in adf["content"]]
    assert "heading" in top_types
    assert "table" in top_types
    assert "codeBlock" in top_types


@responses.activate
def test_update_returns_page_url(client):
    _register_noop_update()
    url = m2c.convert_file(str(EXAMPLES / "basic.md"), client, page_id="P1")
    assert url == f"{BASE_URL}/wiki/spaces/X/pages/P1"


# ---------------------------------------------------------------------------
# Create new page flow
# ---------------------------------------------------------------------------


@responses.activate
def test_create_new_page_posts_then_updates_with_h1_title(client):
    new_id = "NEW1"
    # 1. POST create (returns a fresh page with version=1)
    responses.add(
        responses.POST,
        f"{BASE_URL}/wiki/rest/api/content/",
        json={
            "id": new_id,
            "title": "Heading 1",
            "version": {"number": 1},
            "_links": {"base": BASE_URL, "webui": f"/wiki/spaces/X/pages/{new_id}"},
        },
        status=200,
    )
    # 2. PUT update with full ADF body
    responses.add(
        responses.PUT,
        f"{BASE_URL}/wiki/rest/api/content/{new_id}",
        json=_updated_page(page_id=new_id, version=2, title="Heading 1"),
        status=200,
    )

    url = m2c.convert_file(
        str(EXAMPLES / "basic.md"),
        client,
        parent_id="PARENT",
        space_key="SPACE",
    )

    post_call = [c for c in responses.calls if c.request.method == "POST"][0]
    post_body = json.loads(post_call.request.body)
    # Title derived from the first h1 in basic.md ("Heading 1")
    assert post_body["title"] == "Heading 1"
    assert post_body["space"] == {"key": "SPACE"}
    assert post_body["ancestors"] == [{"id": "PARENT"}]

    # Second call is PUT with the real body
    put_call = [c for c in responses.calls if c.request.method == "PUT"][0]
    put_body = json.loads(put_call.request.body)
    adf = json.loads(put_body["body"]["atlas_doc_format"]["value"])
    assert adf["content"]  # not the placeholder empty doc

    assert url == f"{BASE_URL}/wiki/spaces/X/pages/{new_id}"


# ---------------------------------------------------------------------------
# Attachment upload flow
# ---------------------------------------------------------------------------


@responses.activate
def test_attachment_upload_emits_mediasingle_in_adf(client):
    page_id = "PIMG"
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/rest/api/content/{page_id}",
        json=_existing_page(page_id=page_id),
        status=200,
    )
    # First GET attachments (via get_attachments at orchestrator level) — empty.
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/rest/api/content/{page_id}/child/attachment",
        json={"results": []},
        status=200,
    )
    # POST upload returns a fresh attachment with fileId + collection.
    responses.add(
        responses.POST,
        f"{BASE_URL}/wiki/rest/api/content/{page_id}/child/attachment",
        json={
            "results": [
                {
                    "id": "ATT1",
                    "title": "cat.jpg",
                    "extensions": {
                        "fileId": "MEDIA-XYZ",
                        "collectionName": "contentId-P1",
                    },
                    "metadata": {"comment": "md5:abcdef"},
                }
            ]
        },
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/api/v2/pages/{page_id}/inline-comments",
        json={"results": []},
        status=200,
    )
    responses.add(
        responses.PUT,
        f"{BASE_URL}/wiki/rest/api/content/{page_id}",
        json=_updated_page(page_id=page_id),
        status=200,
    )

    m2c.convert_file(str(EXAMPLES / "images.md"), client, page_id=page_id)

    # The PUT body should contain a mediaSingle node referencing MEDIA-XYZ.
    put_body = json.loads(
        [c for c in responses.calls if c.request.method == "PUT"][0].request.body
    )
    adf = json.loads(put_body["body"]["atlas_doc_format"]["value"])

    def has_media(nodes):
        for n in nodes:
            if n.get("type") == "mediaSingle":
                inner = n.get("content", [{}])[0]
                if inner.get("attrs", {}).get("id") == "MEDIA-XYZ":
                    return True
            if has_media(n.get("content", [])):
                return True
        return False

    assert has_media(adf["content"])


# ---------------------------------------------------------------------------
# Inline-comment re-anchoring
# ---------------------------------------------------------------------------


@responses.activate
def test_comment_reanchoring_applies_annotation_to_new_adf(client, tmp_path):
    """A comment on text that still exists in the new ADF is re-anchored."""
    page_id = "PCMT"
    # Old ADF contains an annotated text range on "UNIQUE_STRING".
    old_adf = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "UNIQUE_STRING",
                        "marks": [
                            {
                                "type": "annotation",
                                "attrs": {
                                    "id": "U1",
                                    "annotationType": "inlineComment",
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }

    # New MD preserves the text — written to a tmp file so we control it.
    md = tmp_path / "c.md"
    md.write_text("UNIQUE_STRING here\n")

    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/rest/api/content/{page_id}",
        json=_existing_page(page_id=page_id, adf=old_adf),
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/rest/api/content/{page_id}/child/attachment",
        json={"results": []},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/api/v2/pages/{page_id}/inline-comments",
        json={
            "results": [
                {
                    "properties": {
                        "inlineMarkerRef": "U1",
                        "inlineOriginalSelection": "UNIQUE_STRING",
                    },
                    "body": {
                        "atlas_doc_format": {
                            "value": json.dumps({"type": "doc", "content": []})
                        }
                    },
                }
            ]
        },
        status=200,
    )
    responses.add(
        responses.PUT,
        f"{BASE_URL}/wiki/rest/api/content/{page_id}",
        json=_updated_page(page_id=page_id),
        status=200,
    )

    m2c.convert_file(str(md), client, page_id=page_id)

    put_body = json.loads(
        [c for c in responses.calls if c.request.method == "PUT"][0].request.body
    )
    adf = json.loads(put_body["body"]["atlas_doc_format"]["value"])

    def find_annotated(nodes):
        for n in nodes:
            if n.get("type") == "text":
                for m in n.get("marks", []):
                    if (
                        m.get("type") == "annotation"
                        and m.get("attrs", {}).get("id") == "U1"
                    ):
                        return n.get("text", "")
            found = find_annotated(n.get("content", []))
            if found:
                return found
        return None

    annotated = find_annotated(adf["content"])
    assert annotated is not None
    assert "UNIQUE_STRING" in annotated


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


@responses.activate
def test_dry_run_update_skips_put(client):
    page_id = "PDRY"
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/rest/api/content/{page_id}",
        json=_existing_page(page_id=page_id),
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/rest/api/content/{page_id}/child/attachment",
        json={"results": []},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/api/v2/pages/{page_id}/inline-comments",
        json={"results": []},
        status=200,
    )

    url = m2c.convert_file(
        str(EXAMPLES / "basic.md"), client, page_id=page_id, dry_run=True
    )

    assert not any(c.request.method == "PUT" for c in responses.calls)
    assert url == f"{BASE_URL}/wiki/spaces/X/pages/{page_id}"


@responses.activate
def test_dry_run_create_makes_no_api_calls(client):
    result = m2c.convert_file(
        str(EXAMPLES / "basic.md"),
        client,
        parent_id="PARENT",
        space_key="SP",
        dry_run=True,
    )
    assert result is None
    assert len(responses.calls) == 0
