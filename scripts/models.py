"""Normalized catalog model and constants.

Providers return plain dictionaries so catalog files remain portable.  This
module centralizes the allowed vocabulary and creates safe default records.
"""

from __future__ import annotations

from typing import Any


ACCESS_TYPES = {
    "public_domain",
    "open_access",
    "creative_commons",
    "author_free",
    "digital_lending",
    "preview",
    "metadata_only",
    "unknown",
}

RESOURCE_TYPES = {"book", "textbook", "article", "thesis", "other"}

FORMAT_TYPES = {
    "azw3",
    "epub",
    "html",
    "mobi",
    "pdf",
    "read",
    "text",
}


def empty_record(*, source: str, source_id: str, title: str) -> dict[str, Any]:
    """Return a complete provider record with conservative access defaults."""

    return {
        "id": f"{source.lower().replace(' ', '_')}:{source_id}",
        "title": title.strip(),
        "subtitle": "",
        "description": "",
        "authors": [],
        "language": "und",
        "year": None,
        "publisher": "",
        "isbn": [],
        "doi": "",
        "subjects": [],
        "source": source,
        "source_url": "",
        "cover_url": "",
        "formats": [],
        "access": "unknown",
        "license": "",
        "verified_legal": False,
        "resource_type": "book",
        "identifiers": {"source_id": source_id},
    }
