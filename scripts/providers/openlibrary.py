"""Low-volume Open Library discovery provider."""

from __future__ import annotations

import os
from typing import Any

from scripts.normalize import clean_record, clean_text
from scripts.providers.base import BaseProvider, ProviderError


class OpenLibraryProvider(BaseProvider):
    name = "Open Library"
    API_URL = "https://openlibrary.org/search.json"
    DEFAULT_QUERIES = (
        "language:spa subject:programming",
        "language:spa subject:mathematics",
        "language:spa subject:computer_science",
        "title:algorithms author:sedgewick",
        '"fundamentos de algoritmia" brassard',
        'language:spa "metodos numericos"',
    )
    FIELDS = ",".join(
        (
            "key",
            "title",
            "author_name",
            "language",
            "first_publish_year",
            "publisher",
            "isbn",
            "cover_i",
            "edition_key",
            "ia",
            "ebook_access",
            "has_fulltext",
            "public_scan_b",
            "availability",
        )
    )

    def fetch(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        limit = self._limit()
        for query in self._queries():
            payload = self.get_json(
                self.API_URL,
                params={"q": query, "fields": self.FIELDS, "limit": limit, "lang": "es"},
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("docs"), list):
                raise ProviderError(f"{self.name}: unexpected API response")
            records.extend(self.parse_doc(doc) for doc in payload["docs"] if isinstance(doc, dict))

        unique: dict[str, dict[str, Any]] = {}
        for record in records:
            if record["title"]:
                unique[record["id"]] = record
        return list(unique.values())

    @classmethod
    def _queries(cls) -> tuple[str, ...]:
        configured = os.getenv("OPENBOOK_OPENLIBRARY_QUERIES", "")
        if not configured.strip():
            return cls.DEFAULT_QUERIES
        return tuple(query.strip() for query in configured.split(";") if query.strip())

    @staticmethod
    def _limit() -> int:
        raw = os.getenv("OPENBOOK_OPENLIBRARY_LIMIT", "100")
        try:
            return max(1, min(int(raw), 500))
        except ValueError as exc:
            raise ProviderError("Open Library: OPENBOOK_OPENLIBRARY_LIMIT must be an integer") from exc

    @classmethod
    def parse_doc(cls, doc: dict[str, Any]) -> dict[str, Any]:
        key = clean_text(doc.get("key"), 200)
        work_id = key.rsplit("/", 1)[-1]
        editions = doc.get("edition_key") or []
        edition_id = clean_text(editions[0], 100) if editions else ""
        archive_ids = doc.get("ia") or []
        archive_id = clean_text(archive_ids[0], 200) if archive_ids else ""
        availability = doc.get("availability") if isinstance(doc.get("availability"), dict) else {}
        access, verified = cls._classify_access(doc, availability)

        formats: list[dict[str, str]] = []
        if access == "open_access" and archive_id:
            formats.append({"type": "read", "url": f"https://archive.org/details/{archive_id}"})

        cover_id = doc.get("cover_i")
        raw = {
            "id": f"openlibrary:{work_id or edition_id}",
            "title": doc.get("title", ""),
            "authors": doc.get("author_name") or [],
            "language": (doc.get("language") or ["und"])[0],
            "year": doc.get("first_publish_year"),
            "publisher": (doc.get("publisher") or [""])[0],
            "isbn": doc.get("isbn") or [],
            "doi": "",
            "subjects": [],
            "source": cls.name,
            "source_url": f"https://openlibrary.org{key}" if key.startswith("/") else "https://openlibrary.org/",
            "cover_url": f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else "",
            "formats": formats,
            "access": access,
            "license": "",
            "verified_legal": verified,
            "resource_type": "book",
            "identifiers": {
                "source_id": work_id or edition_id,
                "openlibrary_work": work_id,
                "openlibrary_edition": edition_id,
                "internet_archive": archive_id,
            },
        }
        return clean_record(raw)

    @staticmethod
    def _classify_access(doc: dict[str, Any], availability: dict[str, Any]) -> tuple[str, bool]:
        ebook_access = clean_text(doc.get("ebook_access"), 40).lower()
        status = clean_text(availability.get("status"), 60).lower()
        if ebook_access == "public" or status in {"open", "full access"}:
            return "open_access", True
        if ebook_access in {"borrowable", "printdisabled"} or "borrow" in status or "waitlist" in status:
            return "digital_lending", True
        if availability.get("is_previewable") or "preview" in status:
            return "preview", True
        return "metadata_only", False
