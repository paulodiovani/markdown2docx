"""Confluence REST API client (v1 for page CRUD + attachments, v2 for comments)."""

import hashlib
import json
import os

import click
import requests

from lib.config import load_config

_HASH_PREFIX = "md5:"


def _file_hash(file_path):
    """Return the hex MD5 digest of a local file."""
    h = hashlib.md5()
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _attachment_media_info(attachment, filename):
    """Extract ADF media info from a Confluence attachment API response dict."""
    ext = attachment.get("extensions", {})
    metadata = attachment.get("metadata", {})
    return {
        "id": attachment.get("id"),
        "filename": attachment.get("title", filename),
        "media_id": ext.get("fileId"),
        "collection": ext.get("collectionName"),
        # Stored hash lets ensure_attachment detect content changes.
        "stored_hash": metadata.get("comment", ""),
    }


# Minimal ADF document used as a placeholder body when creating a new page
# before its real content is ready (e.g. attachments must be uploaded first).
_EMPTY_ADF = {"type": "doc", "version": 1, "content": []}


class ConfluenceClient:
    """Thin wrapper around the Confluence REST API."""

    def __init__(self):
        config, config_path = load_config()
        click.echo(f"Using config: {config_path}", err=True)
        self.email = config["email"]
        self.api_token = config["api_token"]
        self.base_url = config["url"].rstrip("/")
        self.auth = (self.email, self.api_token)

    # ------------------------------------------------------------------
    # Page CRUD (REST API v1 with ADF body)
    # ------------------------------------------------------------------

    def get_page(self, page_id):
        """Fetch a page with its ADF body and version number."""
        url = f"{self.base_url}/wiki/rest/api/content/{page_id}"
        resp = requests.get(
            url,
            params={"expand": "body.atlas_doc_format,version"},
            auth=self.auth,
        )
        resp.raise_for_status()
        return resp.json()

    def get_page_adf(self, page):
        """Extract and parse the ADF document dict from a get_page() response."""
        value = page.get("body", {}).get("atlas_doc_format", {}).get("value", "null")
        return json.loads(value) or _EMPTY_ADF

    def create_page(self, parent_id, space_key, title, adf_doc=None):
        """Create a new page under parent_id in the given space."""
        url = f"{self.base_url}/wiki/rest/api/content/"
        payload = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "ancestors": [{"id": parent_id}],
            "body": {
                "atlas_doc_format": {
                    "value": json.dumps(adf_doc or _EMPTY_ADF),
                    "representation": "atlas_doc_format",
                }
            },
        }
        resp = requests.post(url, json=payload, auth=self.auth)
        resp.raise_for_status()
        return resp.json()

    def update_page(self, page_id, version, title, adf_doc):
        """Replace a page's ADF body, incrementing the version number."""
        url = f"{self.base_url}/wiki/rest/api/content/{page_id}"
        payload = {
            "id": page_id,
            "type": "page",
            "title": title,
            "body": {
                "atlas_doc_format": {
                    "value": json.dumps(adf_doc),
                    "representation": "atlas_doc_format",
                }
            },
            "version": {"number": version + 1},
        }
        resp = requests.put(url, json=payload, auth=self.auth)
        resp.raise_for_status()
        return resp.json()

    def page_url(self, result):
        """Return the browser URL from an API create/update response."""
        links = result.get("_links", {})
        return links.get("base", "") + links.get("webui", "")

    # ------------------------------------------------------------------
    # Inline comments (REST API v2)
    # ------------------------------------------------------------------

    def get_inline_comments(self, page_id):
        """Fetch all open inline comments for a page.

        Each result contains ``properties.inlineMarkerRef`` (the annotation UUID)
        and ``properties.inlineOriginalSelection`` (the highlighted text).
        """
        url = f"{self.base_url}/wiki/api/v2/pages/{page_id}/inline-comments"
        resp = requests.get(
            url,
            params={"status": "current", "resolution-status": "open"},
            auth=self.auth,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])

    # ------------------------------------------------------------------
    # Attachments (REST API v1 — v2 attachment upload is read-only)
    # ------------------------------------------------------------------

    def upload_attachment(self, page_id, file_path):
        """Upload a file as an attachment; return its media info dict.

        Stores an MD5 hash in the attachment comment so future runs can detect
        content changes without re-downloading the remote file.
        """
        url = f"{self.base_url}/wiki/rest/api/content/{page_id}/child/attachment"
        file_hash = _file_hash(file_path)
        with open(file_path, "rb") as fh:
            resp = requests.post(
                url,
                data={"comment": f"{_HASH_PREFIX}{file_hash}"},
                files={"file": (os.path.basename(file_path), fh)},
                headers={"X-Atlassian-Token": "no-check"},
                params={"expand": "extensions,metadata"},
                auth=self.auth,
            )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        att = results[0] if results else {}
        info = _attachment_media_info(att, os.path.basename(file_path))
        if not info["media_id"]:
            click.echo(
                f"  Warning: media_id missing for {info['filename']}. "
                f"extensions={att.get('extensions', {})}",
                err=True,
            )
        return info

    def get_attachments(self, page_id):
        """Return ``{filename: media_info}`` for all attachments on a page.

        Each value is a dict with ``id``, ``media_id``, ``collection`` and
        ``stored_hash`` for change detection.
        """
        url = f"{self.base_url}/wiki/rest/api/content/{page_id}/child/attachment"
        resp = requests.get(
            url, params={"expand": "extensions,metadata"}, auth=self.auth
        )
        resp.raise_for_status()
        return {
            r["title"]: _attachment_media_info(r, r["title"])
            for r in resp.json().get("results", [])
        }

    def update_attachment(self, page_id, attachment_id, file_path):
        """Replace an existing attachment with a new file version, storing its hash."""
        url = (
            f"{self.base_url}/wiki/rest/api/content/{page_id}"
            f"/child/attachment/{attachment_id}/data"
        )
        file_hash = _file_hash(file_path)
        with open(file_path, "rb") as fh:
            resp = requests.post(
                url,
                data={"comment": f"{_HASH_PREFIX}{file_hash}"},
                files={"file": (os.path.basename(file_path), fh)},
                headers={"X-Atlassian-Token": "no-check"},
                params={"expand": "extensions,metadata"},
                auth=self.auth,
            )
        resp.raise_for_status()
        att = resp.json()
        return _attachment_media_info(att, os.path.basename(file_path))

    def ensure_attachment(self, page_id, file_path, existing=None):
        """Return media info for an attachment, uploading/updating only when needed.

        Compares the MD5 hash of the local file against the hash stored in the
        attachment comment (written by a previous upload).  Re-uploads only when
        the content has actually changed, so unchanged images and regenerated
        diagrams that produce identical output are skipped efficiently.

        Pass the result of ``get_attachments()`` as *existing* to avoid an
        extra API call when processing multiple files for the same page.
        """
        filename = os.path.basename(file_path)
        if existing is None:
            existing = self.get_attachments(page_id)
        if filename in existing:
            info = existing[filename]
            stored = info.get("stored_hash", "")
            local_hash = _file_hash(file_path)
            if stored == f"{_HASH_PREFIX}{local_hash}":
                click.echo(f"  Attachment unchanged, skipping: {filename}", err=True)
                return info
            click.echo(f"  Attachment changed, re-uploading: {filename}", err=True)
            return self.update_attachment(page_id, info["id"], file_path)
        click.echo(f"  Uploading attachment: {filename}", err=True)
        return self.upload_attachment(page_id, file_path)
