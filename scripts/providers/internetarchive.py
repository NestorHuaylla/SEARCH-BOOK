"""Conservative Internet Archive metadata provider.

This adapter never exposes generated file URLs.  Explicit Creative Commons or
public-domain metadata is marked open; restricted items are marked as lending;
everything else remains metadata-only.
"""

from __future__ import annotations

import os
from typing import Any

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
        return [self.parse_doc(doc) for doc in docs if isinstance(doc, dict)]

    @staticmethod
    def _limit() -> int:
        raw = os.getenv("OPENBOOK_INTERNET_ARCHIVE_LIMIT", "50")
        try:
            return max(1, min(int(raw), 200))
        except ValueError as exc:
            raise ProviderError("Internet Archive: OPENBOOK_INTERNET_ARCHIVE_LIMIT must be an integer") from exc

    @classmethod
    def parse_doc(cls, doc: dict[str, Any]) -> dict[str, Any]:
        identifier = clean_text(doc.get("identifier"), 300)
        license_url = safe_url(doc.get("licenseurl"))
        rights = clean_text(doc.get("rights"), 300)
        restricted = doc.get("access-restricted-item") is True or normalize_text(doc.get("access-restricted-item")) == "true"
        combined = normalize_text(f"{license_url} {rights}")
        if restricted:
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
            "formats": [],
            "access": access,
            "license": license_label,
            "verified_legal": verified,
            "resource_type": "book",
            "identifiers": {"source_id": identifier, "internet_archive": identifier},
        }
        return clean_record(raw)

