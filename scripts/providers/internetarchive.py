"""Conservative Internet Archive metadata and explicit-file provider.

Only items with explicit Creative Commons/public-domain metadata may expose
files, and every link is derived from a filename returned by the official Item
Metadata API. Restricted, dark or no-download items never expose files.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import quote

from scripts.normalize import clean_record, clean_text, normalize_text, safe_url
from scripts.providers.base import BaseProvider, ProviderError


class InternetArchiveProvider(BaseProvider):
    name = "Internet Archive"
    API_URL = "https://archive.org/advancedsearch.php"
    DEFAULT_QUERY = "mediatype:texts AND language:spa AND licenseurl:*"

    def fetch(self) -> list[dict[str, Any]]:
        query = os.getenv("OPENBOOK_INTERNET_ARCHIVE_QUERY", self.DEFAULT_QUERY).strip()
        payload = self.get_json(
            self.API_URL,
            params={
                "q": query,
                "fl[]": [
                    "identifier",
                    "title",
                    "creator",
                    "year",
                    "date",
                    "language",
                    "subject",
                    "licenseurl",
                    "rights",
                    "access-restricted-item",
                ],
                "rows": self._limit(),
                "page": 1,
                "output": "json",
            },
        )
        response = payload.get("response") if isinstance(payload, dict) else None
        docs = response.get("docs") if isinstance(response, dict) else None
        if not isinstance(docs, list):
            raise ProviderError(f"{self.name}: unexpected Advanced Search response")
        valid_docs = [doc for doc in docs if isinstance(doc, dict)]
        details: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=min(6, len(valid_docs) or 1)) as executor:
            tasks = {
                executor.submit(self._fetch_item, clean_text(doc.get("identifier"), 300)): doc
                for doc in valid_docs
                if clean_text(doc.get("identifier"), 300)
            }
            for future in as_completed(tasks):
                identifier = clean_text(tasks[future].get("identifier"), 300)
                try:
                    payload = future.result()
                    if payload:
                        details[identifier] = payload
                except ProviderError:
                    # The bibliographic record is still useful if one item API
                    # request fails; it simply will not expose direct files.
                    continue
        return [self.parse_doc(doc, details.get(clean_text(doc.get("identifier"), 300))) for doc in valid_docs]

    def _fetch_item(self, identifier: str) -> dict[str, Any]:
        if not identifier:
            return {}
        payload = self.get_json(f"https://archive.org/metadata/{quote(identifier, safe='')}")
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _limit() -> int:
        raw = os.getenv("OPENBOOK_INTERNET_ARCHIVE_LIMIT", "50")
        try:
            return max(1, min(int(raw), 200))
        except ValueError as exc:
            raise ProviderError("Internet Archive: OPENBOOK_INTERNET_ARCHIVE_LIMIT must be an integer") from exc

    @classmethod
    def parse_doc(cls, doc: dict[str, Any], item: dict[str, Any] | None = None) -> dict[str, Any]:
        item = item or {}
        identifier = clean_text(doc.get("identifier"), 300)
        license_url = safe_url(doc.get("licenseurl"))
        rights = clean_text(doc.get("rights"), 300)
        restricted = doc.get("access-restricted-item") is True or normalize_text(doc.get("access-restricted-item")) == "true"
        combined = normalize_text(f"{license_url} {rights}")
        item_metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        no_download = any(
            normalize_text(value) in {"1", "true", "yes"}
            for value in (
                item.get("is_dark"),
                item_metadata.get("nodownload"),
                item_metadata.get("access-restricted-item"),
            )
        )
        if restricted or no_download:
            access, verified = "digital_lending", True
            license_label = rights or "Digital lending; see item page"
        elif "creativecommons org" in combined:
            access, verified = "creative_commons", True
            license_label = license_url
        elif "public domain" in combined:
            access, verified = "public_domain", True
            license_label = rights or "Public domain"
        else:
            access, verified = "metadata_only", False
            license_label = rights

        creators = doc.get("creator") or []
        if isinstance(creators, str):
            creators = [creators]
        subjects = doc.get("subject") or []
        if isinstance(subjects, str):
            subjects = [subjects]
        language = doc.get("language") or "und"
        if isinstance(language, list):
            language = language[0] if language else "und"
        formats = cls.parse_files(identifier, item) if verified and access in {"creative_commons", "public_domain"} else []
        raw = {
            "id": f"internetarchive:{identifier}",
            "title": doc.get("title", ""),
            "authors": creators,
            "language": language,
            "year": doc.get("year") or doc.get("date"),
            "publisher": "",
            "isbn": [],
            "doi": "",
            "subjects": subjects,
            "source": cls.name,
            "source_url": f"https://archive.org/details/{identifier}",
            "cover_url": f"https://archive.org/services/img/{identifier}",
            "formats": formats,
            "access": access,
            "license": license_label,
            "verified_legal": verified,
            "resource_type": "book",
            "identifiers": {"source_id": identifier, "internet_archive": identifier},
        }
        return clean_record(raw)

    @classmethod
    def parse_files(cls, identifier: str, item: dict[str, Any]) -> list[dict[str, str]]:
        """Select at most one explicit, downloadable file per useful format."""

        files = item.get("files") if isinstance(item.get("files"), list) else []
        candidates: list[tuple[int, str, str]] = []
        format_priority = {"pdf": 0, "epub": 1, "html": 2, "text": 3}
        for file in files:
            if not isinstance(file, dict):
                continue
            if any(
                normalize_text(file.get(key)) in {"1", "true", "yes"}
                for key in ("private", "login", "restricted")
            ):
                continue
            name = clean_text(file.get("name"), 1_000)
            label = normalize_text(file.get("format"))
            lower_name = name.lower()
            if not name or name.startswith("."):
                continue
            if lower_name.endswith(".pdf") or "pdf" in label:
                format_type = "pdf"
            elif lower_name.endswith(".epub") or "epub" in label:
                format_type = "epub"
            elif lower_name.endswith((".html", ".htm")) or label == "html":
                format_type = "html"
            elif lower_name.endswith(".txt") and not lower_name.endswith(("_files.xml.txt", "_meta.txt")):
                format_type = "text"
            else:
                continue
            source_rank = 0 if normalize_text(file.get("source")) == "original" else 1
            candidates.append((format_priority[format_type] * 10 + source_rank, format_type, name))

        formats: list[dict[str, str]] = []
        seen_types: set[str] = set()
        for _, format_type, name in sorted(candidates):
            if format_type in seen_types:
                continue
            seen_types.add(format_type)
            encoded_name = quote(name, safe="/")
            formats.append({
                "type": format_type,
                "url": f"https://archive.org/download/{quote(identifier, safe='')}/{encoded_name}",
            })
        return formats
