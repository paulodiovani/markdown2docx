"""Unit tests for lib.confluence.

All HTTP traffic is intercepted by the ``responses`` library — no real
network calls are made. ``load_config`` is patched via the
``mock_confluence_config`` fixture so the client is constructed with
fake credentials pointing at ``https://test.atlassian.net``.
"""

import hashlib
import json
from pathlib import Path

import pytest
import responses
from requests import HTTPError

import lib.confluence as confluence_module
from lib.confluence import (
    ConfluenceClient,
    _attachment_media_info,
    _file_hash,
)

BASE_URL = "https://test.atlassian.net"


@pytest.fixture
def client(mock_confluence_config):
    """Return a ConfluenceClient built from the mocked config."""
    return ConfluenceClient()


@pytest.fixture
def attachment_file(tmp_path):
    path = tmp_path / "photo.png"
    path.write_bytes(b"pretend-png-bytes")
    return path


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


def test_client_init_loads_config(client):
    assert client.email == "test@example.com"
    assert client.api_token == "test-token"
    assert client.base_url == "https://test.atlassian.net"
    assert client.auth == ("test@example.com", "test-token")


def test_client_init_strips_trailing_slash_from_url(monkeypatch):
    def fake_load_config():
        return (
            {
                "email": "a@b.com",
                "api_token": "t",
                "url": "https://x.atlassian.net/",
            },
            Path("/fake"),
        )

    monkeypatch.setattr("lib.confluence.load_config", fake_load_config)
    client = ConfluenceClient()
    assert client.base_url == "https://x.atlassian.net"


# ---------------------------------------------------------------------------
# get_page
# ---------------------------------------------------------------------------


@responses.activate
def test_get_page_calls_correct_url_and_params(client):
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/rest/api/content/123",
        json={"id": "123", "version": {"number": 5}},
        status=200,
    )
    result = client.get_page("123")
    assert result["id"] == "123"
    assert len(responses.calls) == 1
    url = responses.calls[0].request.url
    assert "body.atlas_doc_format" in url
    assert "version" in url


@responses.activate
def test_get_page_raises_on_http_error(client):
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/rest/api/content/404",
        json={"error": "not found"},
        status=404,
    )
    with pytest.raises(HTTPError):
        client.get_page("404")


# ---------------------------------------------------------------------------
# get_page_adf
# ---------------------------------------------------------------------------


def test_get_page_adf_parses_atlas_doc_format(client):
    adf = {"type": "doc", "version": 1, "content": []}
    page = {"body": {"atlas_doc_format": {"value": json.dumps(adf)}}}
    assert client.get_page_adf(page) == adf


def test_get_page_adf_returns_empty_on_null_string(client):
    page = {"body": {"atlas_doc_format": {"value": "null"}}}
    assert client.get_page_adf(page) == confluence_module._EMPTY_ADF


def test_get_page_adf_returns_empty_on_missing_body(client):
    assert client.get_page_adf({}) == confluence_module._EMPTY_ADF


# ---------------------------------------------------------------------------
# create_page
# ---------------------------------------------------------------------------


@responses.activate
def test_create_page_posts_correct_payload(client):
    responses.add(
        responses.POST,
        f"{BASE_URL}/wiki/rest/api/content/",
        json={"id": "999"},
        status=200,
    )
    adf = {"type": "doc", "version": 1, "content": [{"type": "paragraph"}]}
    result = client.create_page("parent-1", "TEST", "New Page", adf_doc=adf)
    assert result == {"id": "999"}

    body = json.loads(responses.calls[0].request.body)
    assert body["type"] == "page"
    assert body["title"] == "New Page"
    assert body["space"] == {"key": "TEST"}
    assert body["ancestors"] == [{"id": "parent-1"}]
    assert body["body"]["atlas_doc_format"]["representation"] == "atlas_doc_format"
    assert json.loads(body["body"]["atlas_doc_format"]["value"]) == adf


@responses.activate
def test_create_page_uses_empty_adf_when_none_passed(client):
    responses.add(
        responses.POST,
        f"{BASE_URL}/wiki/rest/api/content/",
        json={"id": "999"},
        status=200,
    )
    client.create_page("parent", "SPACE", "Title", adf_doc=None)
    body = json.loads(responses.calls[0].request.body)
    assert (
        json.loads(body["body"]["atlas_doc_format"]["value"])
        == confluence_module._EMPTY_ADF
    )


# ---------------------------------------------------------------------------
# update_page
# ---------------------------------------------------------------------------


@responses.activate
def test_update_page_increments_version_and_serializes_adf(client):
    responses.add(
        responses.PUT,
        f"{BASE_URL}/wiki/rest/api/content/55",
        json={"id": "55"},
        status=200,
    )
    adf = {"type": "doc", "version": 1, "content": []}
    client.update_page("55", version=5, title="Updated", adf_doc=adf)

    body = json.loads(responses.calls[0].request.body)
    assert body["id"] == "55"
    assert body["title"] == "Updated"
    assert body["version"] == {"number": 6}
    assert json.loads(body["body"]["atlas_doc_format"]["value"]) == adf


# ---------------------------------------------------------------------------
# page_url
# ---------------------------------------------------------------------------


def test_page_url_concatenates_base_and_webui(client):
    result = {"_links": {"base": "https://x.atlassian.net/wiki", "webui": "/pages/123"}}
    assert client.page_url(result) == "https://x.atlassian.net/wiki/pages/123"


def test_page_url_returns_empty_when_no_links(client):
    assert client.page_url({}) == ""


def test_page_url_handles_partial_links(client):
    assert client.page_url({"_links": {"base": "x"}}) == "x"
    assert client.page_url({"_links": {"webui": "y"}}) == "y"


# ---------------------------------------------------------------------------
# get_inline_comments
# ---------------------------------------------------------------------------


@responses.activate
def test_get_inline_comments_uses_v2_url_and_params(client):
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/api/v2/pages/123/inline-comments",
        json={"results": [{"id": "c1"}]},
        status=200,
    )
    result = client.get_inline_comments("123")
    assert result == [{"id": "c1"}]

    url = responses.calls[0].request.url
    assert "status=current" in url
    assert "resolution-status=open" in url
    assert "body-format=atlas_doc_format" in url


@responses.activate
def test_get_inline_comments_returns_empty_list_when_no_results(client):
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/api/v2/pages/123/inline-comments",
        json={},
        status=200,
    )
    assert client.get_inline_comments("123") == []


# ---------------------------------------------------------------------------
# upload_attachment
# ---------------------------------------------------------------------------


@responses.activate
def test_upload_attachment_posts_multipart_with_hash(client, attachment_file):
    expected_hash = hashlib.md5(attachment_file.read_bytes()).hexdigest()
    responses.add(
        responses.POST,
        f"{BASE_URL}/wiki/rest/api/content/123/child/attachment",
        json={
            "results": [
                {
                    "id": "att-1",
                    "title": "photo.png",
                    "extensions": {
                        "fileId": "media-1",
                        "collectionName": "coll-1",
                    },
                    "metadata": {"comment": f"md5:{expected_hash}"},
                }
            ]
        },
        status=200,
    )
    info = client.upload_attachment("123", attachment_file)

    assert info == {
        "id": "att-1",
        "filename": "photo.png",
        "media_id": "media-1",
        "collection": "coll-1",
        "stored_hash": f"md5:{expected_hash}",
    }
    req = responses.calls[0].request
    assert req.headers["X-Atlassian-Token"] == "no-check"
    assert b"photo.png" in req.body
    assert f"md5:{expected_hash}".encode() in req.body


# ---------------------------------------------------------------------------
# get_attachments
# ---------------------------------------------------------------------------


@responses.activate
def test_get_attachments_returns_filename_keyed_dict(client):
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/rest/api/content/123/child/attachment",
        json={
            "results": [
                {
                    "id": "a1",
                    "title": "one.png",
                    "extensions": {"fileId": "m1", "collectionName": "c1"},
                    "metadata": {"comment": "md5:abc"},
                },
                {
                    "id": "a2",
                    "title": "two.jpg",
                    "extensions": {"fileId": "m2", "collectionName": "c1"},
                    "metadata": {"comment": ""},
                },
            ]
        },
        status=200,
    )
    result = client.get_attachments("123")
    assert set(result.keys()) == {"one.png", "two.jpg"}
    assert result["one.png"]["media_id"] == "m1"
    assert result["two.jpg"]["stored_hash"] == ""


# ---------------------------------------------------------------------------
# update_attachment
# ---------------------------------------------------------------------------


@responses.activate
def test_update_attachment_uses_data_subpath(client, attachment_file):
    expected_hash = hashlib.md5(attachment_file.read_bytes()).hexdigest()
    responses.add(
        responses.POST,
        f"{BASE_URL}/wiki/rest/api/content/123/child/attachment/att-1/data",
        json={
            "id": "att-1",
            "title": "photo.png",
            "extensions": {"fileId": "media-2", "collectionName": "coll-1"},
            "metadata": {"comment": f"md5:{expected_hash}"},
        },
        status=200,
    )
    info = client.update_attachment("123", "att-1", attachment_file)
    assert info["id"] == "att-1"
    assert info["media_id"] == "media-2"
    assert info["stored_hash"] == f"md5:{expected_hash}"


# ---------------------------------------------------------------------------
# ensure_attachment
# ---------------------------------------------------------------------------


@responses.activate
def test_ensure_attachment_skips_when_hash_matches(client, attachment_file):
    expected_hash = hashlib.md5(attachment_file.read_bytes()).hexdigest()
    existing = {
        attachment_file.name: {
            "id": "att-1",
            "filename": attachment_file.name,
            "media_id": "m1",
            "collection": "c1",
            "stored_hash": f"md5:{expected_hash}",
        }
    }
    result = client.ensure_attachment("123", attachment_file, existing=existing)
    assert result == existing[attachment_file.name]
    assert len(responses.calls) == 0


@responses.activate
def test_ensure_attachment_reuploads_when_hash_differs(client, attachment_file):
    existing = {
        attachment_file.name: {
            "id": "att-1",
            "filename": attachment_file.name,
            "media_id": "m1",
            "collection": "c1",
            "stored_hash": "md5:STALE",
        }
    }
    responses.add(
        responses.POST,
        f"{BASE_URL}/wiki/rest/api/content/123/child/attachment/att-1/data",
        json={
            "id": "att-1",
            "title": attachment_file.name,
            "extensions": {"fileId": "m2", "collectionName": "c1"},
            "metadata": {"comment": "md5:NEW"},
        },
        status=200,
    )
    result = client.ensure_attachment("123", attachment_file, existing=existing)
    assert result["media_id"] == "m2"
    assert len(responses.calls) == 1


@responses.activate
def test_ensure_attachment_uploads_new_when_filename_absent(client, attachment_file):
    responses.add(
        responses.POST,
        f"{BASE_URL}/wiki/rest/api/content/123/child/attachment",
        json={
            "results": [
                {
                    "id": "new",
                    "title": attachment_file.name,
                    "extensions": {"fileId": "mX", "collectionName": "cX"},
                    "metadata": {"comment": "md5:abc"},
                }
            ]
        },
        status=200,
    )
    result = client.ensure_attachment("123", attachment_file, existing={})
    assert result["id"] == "new"


@responses.activate
def test_ensure_attachment_fetches_existing_when_none(client, attachment_file):
    """When existing is None, ensure_attachment calls get_attachments first."""
    responses.add(
        responses.GET,
        f"{BASE_URL}/wiki/rest/api/content/123/child/attachment",
        json={"results": []},
        status=200,
    )
    responses.add(
        responses.POST,
        f"{BASE_URL}/wiki/rest/api/content/123/child/attachment",
        json={
            "results": [
                {
                    "id": "new",
                    "title": attachment_file.name,
                    "extensions": {"fileId": "m", "collectionName": "c"},
                    "metadata": {"comment": "md5:abc"},
                }
            ]
        },
        status=200,
    )
    client.ensure_attachment("123", attachment_file, existing=None)
    assert len(responses.calls) == 2


# ---------------------------------------------------------------------------
# _file_hash
# ---------------------------------------------------------------------------


def test_file_hash_matches_reference_md5(tmp_path):
    path = tmp_path / "x.bin"
    path.write_bytes(b"hello world")
    assert _file_hash(path) == hashlib.md5(b"hello world").hexdigest()


def test_file_hash_handles_multichunk_file(tmp_path):
    # _file_hash reads 64KiB chunks; use >3 chunks to exercise the loop.
    path = tmp_path / "big.bin"
    data = b"A" * (65536 * 3 + 17)
    path.write_bytes(data)
    assert _file_hash(path) == hashlib.md5(data).hexdigest()


# ---------------------------------------------------------------------------
# _attachment_media_info
# ---------------------------------------------------------------------------


def test_attachment_media_info_extracts_all_fields():
    att = {
        "id": "att-1",
        "title": "foo.png",
        "extensions": {"fileId": "mid", "collectionName": "coll"},
        "metadata": {"comment": "md5:abc"},
    }
    assert _attachment_media_info(att, "foo.png") == {
        "id": "att-1",
        "filename": "foo.png",
        "media_id": "mid",
        "collection": "coll",
        "stored_hash": "md5:abc",
    }


def test_attachment_media_info_uses_filename_fallback():
    info = _attachment_media_info({"id": "att-1"}, "fallback.png")
    assert info["filename"] == "fallback.png"
    assert info["media_id"] is None
    assert info["collection"] is None


def test_attachment_media_info_empty_hash_when_no_metadata():
    att = {
        "id": "1",
        "title": "x.png",
        "extensions": {"fileId": "m", "collectionName": "c"},
    }
    assert _attachment_media_info(att, "x.png")["stored_hash"] == ""
