"""Kaggle: public dataset search through the official remote MCP server, and
the one publisher this skill ships, driven through the official CLI.

The only module of this skill that names the service. Search uses the MCP
server's public ``search_datasets`` tool, which answers without a token.
Publishing shells out to the official ``kaggle`` client, which finds the
token itself (``~/.kaggle/access_token`` or ``KAGGLE_API_TOKEN``): nothing
here reads, copies, prints or passes a credential.
"""

from __future__ import annotations

import json
import re

NAME = "kaggle"
MCP_URL = "https://www.kaggle.com/mcp"
SEARCH_TOOL = "search_datasets"


def _payload(text):
    """The JSON-RPC body, whether the server answered JSON or SSE ``data:`` lines."""
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return json.loads(text)


def search(query, http, limit=20):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": SEARCH_TOOL, "arguments": {"request": {"search": query}}}})
    _status, text = http("POST", MCP_URL, body=body, headers={
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    result = (_payload(text) or {}).get("result") or {}
    if result.get("isError"):
        raise OSError("search rejected by the MCP server")
    items = []
    for part in result.get("content") or []:
        if not isinstance(part, dict) or not part.get("text"):
            continue
        try:
            decoded = json.loads(part["text"])
        except ValueError:
            continue
        if isinstance(decoded, dict):
            decoded = decoded.get("datasets") or decoded.get("items") or []
        if isinstance(decoded, list):
            items.extend(item for item in decoded if isinstance(item, dict))
    hits = []
    for item in items:
        ref = item.get("ref") or item.get("datasetRef") or ""
        if not ref:
            continue
        hits.append({"ref": ref, "title": item.get("title") or ref,
                     "license": item.get("licenseName") or item.get("license") or "",
                     "url": item.get("url") or f"https://www.kaggle.com/datasets/{ref}"})
    return hits[:limit]


_DATASET_URL = re.compile(
    r"^https?://(?:www\.)?kaggle\.com/datasets/([A-Za-z0-9_-]+)/([a-z0-9][a-z0-9-]*[a-z0-9])/?(?:[?#].*)?$")


def ref_from_url(url):
    """The ``owner/slug`` a public dataset page names, or ``None`` when the
    URL is not one of this host's dataset pages. A job's runner attaches a
    dataset by this ref (``remote_cli generate-job --dataset``)."""
    match = _DATASET_URL.match(str(url or "").strip())
    return f"{match.group(1)}/{match.group(2)}" if match else None


class _Publisher:
    """Command lines for the official client and the metadata it accepts."""

    client = "kaggle"
    metadata_file = "dataset-metadata.json"
    licenses = ("CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "CC-BY-NC-4.0", "CC-BY-NC-SA-4.0",
                "ODbL-1.0", "other")

    def status_argv(self, ref):
        return [self.client, "datasets", "status", ref]

    def create_argv(self, folder, public=False):
        # Private by default: `-u` (public) only when the caller passed both gates.
        return [self.client, "datasets", "create", "-p", folder] + (["-u"] if public else [])

    def version_argv(self, folder, notes):
        return [self.client, "datasets", "version", "-p", folder, "-m", notes]

    def validate_metadata(self, meta):
        problems = []
        if not 6 <= len(meta.get("title", "")) <= 50:
            problems.append("title must be 6-50 characters")
        subtitle = meta.get("subtitle", "")
        if subtitle and not 20 <= len(subtitle) <= 80:
            problems.append("subtitle must be 20-80 characters")
        if not re.fullmatch(r"[A-Za-z0-9_-]+/[a-z0-9][a-z0-9-]{1,48}[a-z0-9]", meta.get("id", "")):
            problems.append("id must be owner/slug")
        names = [item.get("name") for item in meta.get("licenses") or []]
        if len(names) != 1 or names[0] not in self.licenses:
            problems.append(f"licenses must be one of {list(self.licenses)}")
        return problems

    def mount_hint(self, ref):
        slug = ref.split("/", 1)[1]
        return (f"Attach {ref} to the notebook as an input; it mounts read-only under "
                f"/kaggle/input/ (often /kaggle/input/{slug}/, but the path can differ), so "
                "discover it with: import os; [print(r, f) for r, _d, f in os.walk('/kaggle/input')]")


PUBLISHER = _Publisher()
