"""Project Gutenberg metadata through the documented Gutendex API."""

from __future__ import annotations

import os
from typing import Any

from scripts.normalize import clean_record, safe_url
from scripts.providers.base import BaseProvider, ProviderError


class GutenbergProvider(BaseProvider):
    name = "Project Gutenberg"
    API_URL = "https://gutendex.com/books/"
    MIME_FORMATS = {
        "application/epub+zip": "epub",
        "application/pdf": "pdf",
        "application/x-mobipocket-ebook": "mobi",
        "text/html": "html",
        "text/plain": "text",
    }

    def fetch(self) -> list[dict[str, Any]]:
        max_pages = self._max_pages()
        url: str | None = self.API_URL
        records: list[dict[str, Any]] = []
        pages = 0
        while url and pages < max_pages:
            payload = self.get_json(url)
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                raise ProviderError(f"{self.name}: unexpected API response")
            records.extend(self.parse_book(item) for item in payload["results"] if isinstance(item, dict))
            next_url = safe_url(payload.get("next"))
            url = next_url or None
            pages += 1
        return [record for record in records if record["title"]]

    @staticmethod
    def _max_pages() -> int:
        raw = os.getenv("OPENBOOK_GUTENBERG_MAX_PAGES", "10")
        try:
            return max(1, min(int(raw), 500))
        except ValueError as exc:
            raise ProviderError("Project Gutenberg: OPENBOOK_GUTENBERG_MAX_PAGES must be an integer") from exc

    @classmethod
    def parse_book(cls, item: dict[str, Any]) -> dict[str, Any]:
        gutenberg_id = str(item.get("id", ""))
        api_formats = item.get("formats") if isinstance(item.get("formats"), dict) else {}
        is_public_domain = item.get("copyright") is False
        formats: list[dict[str, str]] = []
        cover_url = ""
        for mime_type, raw_url in api_formats.items():
            url = safe_url(raw_url)
            if not url:
                continue
            base_mime = str(mime_type).split(";", 1)[0].lower()
            if base_mime == "image/jpeg":
                cover_url = url
            elif is_public_domain and base_mime in cls.MIME_FORMATS:
                formats.append({"type": cls.MIME_FORMATS[base_mime], "url": url})

        authors = [author.get("name", "") for author in item.get("authors", []) if isinstance(author, dict)]
        subjects = [*item.get("subjects", []), *item.get("bookshelves", [])]
        raw = {
            "id": f"gutenberg:{gutenberg_id}",
            "title": item.get("title", ""),
            "authors": authors,
            "language": (item.get("languages") or ["und"])[0],
            "year": None,
            "publisher": "Project Gutenberg",
            "isbn": [],
            "doi": "",
            "subjects": subjects,
            "source": cls.name,
            "source_url": f"https://www.gutenberg.org/ebooks/{gutenberg_id}",
            "cover_url": cover_url,
            "formats": formats,
            "access": "public_domain" if is_public_domain else "metadata_only",
            "license": "Public domain in the United States" if is_public_domain else "",
            "verified_legal": is_public_domain,
            "resource_type": "book",
            "identifiers": {"source_id": gutenberg_id, "gutenberg_id": gutenberg_id},
        }
        return clean_record(raw)
