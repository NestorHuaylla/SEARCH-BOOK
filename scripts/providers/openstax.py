"""OpenStax provider using the public CMS book endpoints."""

from __future__ import annotations

import logging
import os
from typing import Any

from scripts.normalize import clean_record, clean_text, safe_url
from scripts.providers.base import BaseProvider, ProviderError


LOGGER = logging.getLogger("openbook.sync")


class OpenStaxProvider(BaseProvider):
    name = "OpenStax"
    API_URL = "https://openstax.org/apps/cms/api/books"

    def fetch(self) -> list[dict[str, Any]]:
        payload = self.get_json(self.API_URL)
        items = payload.get("books") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise ProviderError(f"{self.name}: unexpected CMS response")

        max_books = self._max_books(len(items))
        include_details = os.getenv("OPENBOOK_OPENSTAX_FETCH_DETAILS", "1").strip() != "0"
        records: list[dict[str, Any]] = []
        for item in items[:max_books]:
            if not isinstance(item, dict):
                continue
            details: dict[str, Any] = {}
            slug = clean_text(item.get("slug"), 300).strip("/")
            if include_details and slug:
                try:
                    response = self.get_json(f"https://openstax.org/apps/cms/api/{slug}")
                    if isinstance(response, dict):
                        details = response
                except ProviderError as exc:
                    LOGGER.warning("OpenStax detail %s failed: %s", slug, exc)
            record = self.parse_book(item, details)
            if record["title"]:
                records.append(record)
        return records

    @staticmethod
    def _max_books(total: int) -> int:
        raw = os.getenv("OPENBOOK_OPENSTAX_MAX_BOOKS", "0")
        try:
            value = int(raw)
        except ValueError as exc:
            raise ProviderError("OpenStax: OPENBOOK_OPENSTAX_MAX_BOOKS must be an integer") from exc
        return total if value <= 0 else min(value, total)

    @classmethod
    def parse_book(cls, summary: dict[str, Any], details: dict[str, Any] | None = None) -> dict[str, Any]:
        details = details or {}
        slug = clean_text(summary.get("slug"), 300).strip("/")
        slug_id = slug.removeprefix("books/")
        authors: list[str] = []
        for item in details.get("authors") or []:
            if not isinstance(item, dict):
                continue
            value = item.get("value") if isinstance(item.get("value"), dict) else {}
            if value.get("name"):
                authors.append(value["name"])

        subjects = [
            *(summary.get("subjects") or []),
            *(summary.get("subject_categories") or []),
            *(details.get("book_subjects") or []),
            *(details.get("book_categories") or []),
        ]
        formats: list[dict[str, str]] = []
        pdf_url = safe_url(details.get("pdf_url") or summary.get("pdf_url"))
        read_url = safe_url(details.get("webview_rex_link") or summary.get("webview_rex_link"))
        if pdf_url:
            formats.append({"type": "pdf", "url": pdf_url})
        if read_url:
            formats.append({"type": "read", "url": read_url})

        license_url = safe_url(details.get("license_url"))
        license_name = clean_text(details.get("license_name"), 100)
        license_version = clean_text(details.get("license_version"), 30)
        license_label = " ".join(part for part in (license_name, license_version) if part)
        if not license_label:
            license_label = "Openly licensed; see official book page"
        access = "creative_commons" if "creativecommons.org" in license_url else "open_access"

        isbn = [
            details.get("digital_isbn_13"),
            details.get("print_isbn_13"),
            details.get("print_softcover_isbn_13"),
            details.get("assignable_isbn_13"),
        ]
        book_id = clean_text(details.get("book_uuid") or summary.get("id") or slug_id, 200)
        source_url = f"https://openstax.org/details/{slug}" if slug else "https://openstax.org/subjects"
        raw = {
            "id": f"openstax:{book_id}",
            "title": details.get("title") or summary.get("title", ""),
            "authors": authors,
            "language": details.get("meta", {}).get("locale", "en") if isinstance(details.get("meta"), dict) else "en",
            "year": details.get("publish_date"),
            "publisher": "OpenStax, Rice University",
            "isbn": [value for value in isbn if value],
            "doi": "",
            "subjects": subjects,
            "source": cls.name,
            "source_url": source_url,
            "cover_url": details.get("cover_url") or summary.get("cover_url", ""),
            "formats": formats,
            "access": access,
            "license": license_label,
            "verified_legal": True,
            "resource_type": "textbook",
            "identifiers": {
                "source_id": book_id,
                "openstax_slug": slug_id,
                "license_url": license_url,
            },
        }
        return clean_record(raw)

