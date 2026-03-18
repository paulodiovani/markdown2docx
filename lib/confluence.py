"""Confluence REST API v1 client."""

import os

import click
import requests
from dotenv import load_dotenv


class ConfluenceClient:
    """Thin wrapper around the Confluence REST API v1."""

    def __init__(self):
        load_dotenv()
        self.email = os.environ["CONFLUENCE_EMAIL"]
        self.api_token = os.environ["CONFLUENCE_API_TOKEN"]
        self.base_url = os.environ["CONFLUENCE_URL"].rstrip("/")
        self.auth = (self.email, self.api_token)

    def get_page(self, page_id):
        """Fetch a page with its current body and version number."""
        url = f"{self.base_url}/wiki/rest/api/content/{page_id}"
        resp = requests.get(
            url,
            params={"expand": "body.storage,version"},
            auth=self.auth,
        )
        resp.raise_for_status()
        return resp.json()

    def create_page(self, parent_id, space_key, title, body):
        """Create a new page under parent_id in the given space."""
        url = f"{self.base_url}/wiki/rest/api/content/"
        payload = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "ancestors": [{"id": parent_id}],
            "body": {
                "storage": {
                    "value": body,
                    "representation": "storage",
                }
            },
        }
        resp = requests.post(url, json=payload, auth=self.auth)
        resp.raise_for_status()
        return resp.json()

    def update_page(self, page_id, version, title, body):
        """Replace a page's body, incrementing the version number.

        WARNING: Updating the page body will resolve any inline comments whose
        anchored text no longer matches the new content. This is a Confluence
        limitation and cannot be avoided programmatically.
        """
        url = f"{self.base_url}/wiki/rest/api/content/{page_id}"
        payload = {
            "id": page_id,
            "type": "page",
            "title": title,
            "body": {
                "storage": {
                    "value": body,
                    "representation": "storage",
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

    def upload_attachment(self, page_id, file_path):
        """Upload a file as an attachment to the given page.

        Returns the attachment filename as stored by Confluence.
        """
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
        if results:
            return results[0]["title"]
        return os.path.basename(file_path)

    def get_attachments(self, page_id):
        """Return a dict of {filename: attachment_id} for an existing page."""
        url = f"{self.base_url}/wiki/rest/api/content/{page_id}/child/attachment"
        resp = requests.get(url, auth=self.auth)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return {r["title"]: r["id"] for r in results}

    def update_attachment(self, page_id, attachment_id, file_path):
        """Replace an existing attachment with a new version of the file."""
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

        Pass the result of get_attachments() as `existing` to avoid an extra
        API call when processing multiple files for the same page.
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
