"""Free Programming Books provider using its official raw Markdown list."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from scripts.normalize import clean_record, clean_text, normalize_text, safe_url
from scripts.providers.base import BaseProvider, ProviderError


class FreeProgrammingBooksProvider(BaseProvider):
    name = "Free Programming Books"
    SPANISH_URL = (
        "https://raw.githubusercontent.com/EbookFoundation/free-programming-books/"
        "main/books/free-programming-books-es.md"
    )
    LICENSE_URL = (
        "https://github.com/EbookFoundation/free-programming-books/"
        "blob/main/LICENSE"
    )

    def fetch(self) -> list[dict[str, Any]]:
        response = self.get(self.SPANISH_URL, headers={"Accept": "text/plain"})
        try:
            markdown = response.content.decode("utf-8")
            return self.parse_markdown(markdown, language="es")
        except (TypeError, ValueError, UnicodeDecodeError) as exc:
            raise ProviderError(f"{self.name}: could not parse Markdown: {exc}") from exc

    @classmethod
    def parse_markdown(cls, markdown: str, *, language: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        section = "Programación"
        in_index = False

        for raw_line in markdown.splitlines():
            line = raw_line.strip()
            heading = re.match(r"^(#{2,5})\s+(.+?)\s*$", line)
            if heading:
                heading_text = clean_text(heading.group(2))
                in_index = normalize_text(heading_text) == "index"
                if not in_index:
                    section = heading_text
                continue
            if in_index or not line.startswith("*"):
                continue

            parsed = cls._parse_list_item(line)
            if not parsed:
                continue
            title, url, tail = parsed
            source_url = safe_url(url)
            if not source_url:
                continue

            metadata_tokens = " ".join(re.findall(r"\(([^)]*)\)", tail))
            metadata_norm = normalize_text(metadata_tokens)
            authors = cls._parse_authors(tail)
            formats = cls._formats_for(source_url, tail, metadata_norm)
            license_name = cls._license_from(metadata_tokens)
            access = "creative_commons" if license_name else "author_free"
            source_id = hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:20]

            raw = {
                "id": f"free_programming_books:{source_id}",
                "title": title,
                "authors": authors,
                "language": language,
                "year": None,
                "publisher": "",
                "isbn": [],
                "doi": "",
                "subjects": ["Programación", section],
                "source": cls.name,
                "source_url": source_url,
                "cover_url": "",
                "formats": formats,
                "access": access,
                "license": license_name,
                "verified_legal": True,
                "resource_type": "book",
                "identifiers": {
                    "source_id": source_id,
                    "list_url": cls.SPANISH_URL,
                },
            }
            records.append(clean_record(raw))
        return records

    @staticmethod
    def _parse_list_item(line: str) -> tuple[str, str, str] | None:
        match = re.match(r"^\*\s+\[([^]]+)]\(", line)
        if not match:
            return None
        title = clean_text(match.group(1))
        url_start = match.end()
        depth = 1
        cursor = url_start
        while cursor < len(line) and depth:
            char = line[cursor]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            cursor += 1
        if depth or cursor <= url_start + 1:
            return None
        url = line[url_start : cursor - 1].strip()
        tail = re.sub(r"^\s*-\s*", "", line[cursor:]).strip()
        return title, url, tail

    @staticmethod
    def _parse_authors(tail: str) -> list[str]:
        if not tail:
            return []
        without_links = re.sub(
            r"\[([^]]*)]\(https?://[^)]+\)",
            r"\1",
            tail,
            flags=re.IGNORECASE,
        )
        without_metadata = re.sub(
            r"\s*\((?:PDF|HTML|EPUB|GitHub|CC[^)]*|descarga directa|en proceso)[^)]*\)",
            "",
            without_links,
            flags=re.IGNORECASE,
        )
        without_metadata = clean_text(without_metadata)
        if not without_metadata:
            return []
        values = re.split(r"\s*,\s*(?=(?:[^.]*\s)?[A-ZÁÉÍÓÚÑ])|\s+et al\.?$", without_metadata)
        return [value for value in (clean_text(item) for item in values) if value]

    @staticmethod
    def _formats_for(url: str, tail: str, metadata: str) -> list[dict[str, str]]:
        formats: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for label, linked_url in re.findall(
            r"\[([^]]+)]\((https?://[^)]+)\)",
            tail,
            flags=re.IGNORECASE,
        ):
            normalized_label = normalize_text(label)
            for format_type in ("pdf", "epub", "html"):
                if format_type in normalized_label:
                    safe_link = safe_url(linked_url)
                    key = (format_type, safe_link)
                    if safe_link and key not in seen:
                        seen.add(key)
                        formats.append({"type": format_type, "url": safe_link})
        lower_url = url.lower().split("?", 1)[0]
        candidates = {
            "pdf": ("pdf" in metadata and not any(item["type"] == "pdf" for item in formats)) or lower_url.endswith(".pdf"),
            "epub": ("epub" in metadata and not any(item["type"] == "epub" for item in formats)) or lower_url.endswith(".epub"),
            "html": ("html" in metadata and not any(item["type"] == "html" for item in formats)),
        }
        for format_type, present in candidates.items():
            if present and (format_type, url) not in seen:
                seen.add((format_type, url))
                formats.append({"type": format_type, "url": url})
        return formats

    @staticmethod
    def _license_from(value: str) -> str:
        match = re.search(
            r"\b(CC(?:0|\s+BY(?:-NC)?(?:-ND|-SA)?)(?:\s+\d\.\d)?)\b",
            value,
            flags=re.IGNORECASE,
        )
        return clean_text(match.group(1)).upper() if match else ""
