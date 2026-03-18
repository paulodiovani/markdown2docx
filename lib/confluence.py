"""Confluence REST API client (v1 for page CRUD + attachments, v2 for comments)."""

import json
import os

import click
import requests
from dotenv import load_dotenv

# Minimal ADF document used as a placeholder body when creating a new page
# before its real content is ready (e.g. attachments must be uploaded first).
_EMPTY_ADF = {"type": "doc", "version": 1, "content": []}


class ConfluenceClient:
    """Thin wrapper around the Confluence REST API."""

    def __init__(self):
        load_dotenv()
        self.email = os.environ["CONFLUENCE_EMAIL"]
        self.api_token = os.environ["CONFLUENCE_API_TOKEN"]
        self.base_url = os.environ["CONFLUENCE_URL"].rstrip("/")
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
        """Upload a file as an attachment; return the stored filename."""
        url = f"{self.base_url}/wiki/rest/api/content/{page_id}/child/attachment"
        with open(file_path, "rb") as fh:
            resp = requests.post(
                url,
                files={"file": (os.path.basename(file_path), fh)},
                headers={"X-Atlassian-Token": "no-check"},
                auth=self.auth,
            )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0]["title"] if results else os.path.basename(file_path)

    def get_attachments(self, page_id):
        """Return ``{filename: attachment_id}`` for an existing page."""
        url = f"{self.base_url}/wiki/rest/api/content/{page_id}/child/attachment"
        resp = requests.get(url, auth=self.auth)
        resp.raise_for_status()
        return {r["title"]: r["id"] for r in resp.json().get("results", [])}

    def update_attachment(self, page_id, attachment_id, file_path):
        """Replace an existing attachment with a new file version."""
        url = (
            f"{self.base_url}/wiki/rest/api/content/{page_id}"
            f"/child/attachment/{attachment_id}/data"
        )
        with open(file_path, "rb") as fh:
            resp = requests.post(
                url,
                files={"file": (os.path.basename(file_path), fh)},
                headers={"X-Atlassian-Token": "no-check"},
                auth=self.auth,
            )
        resp.raise_for_status()
        return resp.json()

    def ensure_attachment(self, page_id, file_path, existing=None):
        """Upload or update an attachment; return the stored filename.

        Pass the result of ``get_attachments()`` as *existing* to avoid an
        extra API call when processing multiple files for the same page.
        """
        filename = os.path.basename(file_path)
        if existing is None:
            existing = self.get_attachments(page_id)
        if filename in existing:
            click.echo(f"  Updating attachment: {filename}", err=True)
            self.update_attachment(page_id, existing[filename], file_path)
        else:
            click.echo(f"  Uploading attachment: {filename}", err=True)
            self.upload_attachment(page_id, file_path)
        return filename
