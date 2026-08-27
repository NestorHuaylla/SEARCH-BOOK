"""OpenAlex provider restricted to confirmed Open Access locations."""

from __future__ import annotations

import os
from typing import Any

from scripts.normalize import clean_record, clean_text, normalize_doi, normalize_text, safe_url
from scripts.providers.base import BaseProvider, ProviderError


class OpenAlexProvider(BaseProvider):
    name = "OpenAlex"
    API_URL = "https://api.openalex.org/works"
    DEFAULT_QUERIES = ("numerical methods", "algorithms", "computer science", "mathematics")
    SELECT = ",".join(
        (
            "id",
            "doi",
            "title",
            "authorships",
            "publication_year",
            "best_oa_location",
            "open_access",
            "topics",
            "language",
            "type",
        )
    )

    def fetch(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for query in self._queries():
            params = {
                "search": query,
                "filter": "open_access.is_oa:true,has_oa_accepted_or_published_version:true",
                "per_page": self._limit(),
                "select": self.SELECT,
            }
            if self.settings.openalex_api_key:
                params["api_key"] = self.settings.openalex_api_key
            if self.settings.contact_email:
                params["mailto"] = self.settings.contact_email
            payload = self.get_json(self.API_URL, params=params)
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                raise ProviderError(f"{self.name}: unexpected API response")
            records.extend(self.parse_work(item) for item in payload["results"] if isinstance(item, dict))

        unique = {record["id"]: record for record in records if record["title"] and record["verified_legal"]}
        return list(unique.values())

    @classmethod
    def _queries(cls) -> tuple[str, ...]:
        raw = os.getenv("OPENBOOK_OPENALEX_QUERIES", "")
        return tuple(value.strip() for value in raw.split(";") if value.strip()) or cls.DEFAULT_QUERIES

    @staticmethod
    def _limit() -> int:
        raw = os.getenv("OPENBOOK_OPENALEX_LIMIT", "25")
        try:
            return max(1, min(int(raw), 100))
        except ValueError as exc:
            raise ProviderError("OpenAlex: OPENBOOK_OPENALEX_LIMIT must be an integer") from exc

    @classmethod
    def parse_work(cls, item: dict[str, Any]) -> dict[str, Any]:
        location = item.get("best_oa_location") if isinstance(item.get("best_oa_location"), dict) else {}
        open_access = item.get("open_access") if isinstance(item.get("open_access"), dict) else {}
        is_oa = bool(location.get("is_oa")) and bool(open_access.get("is_oa"))
        landing_url = safe_url(location.get("landing_page_url"))
        pdf_url = safe_url(location.get("pdf_url"))
        openalex_url = safe_url(item.get("id"))
        doi = normalize_doi(item.get("doi"))
        source_url = landing_url or (f"https://doi.org/{doi}" if doi else openalex_url)
        formats = [{"type": "pdf", "url": pdf_url}] if is_oa and pdf_url else []

        authors = []
        for authorship in item.get("authorships") or []:
            author = authorship.get("author") if isinstance(authorship, dict) else None
            if isinstance(author, dict) and author.get("display_name"):
                authors.append(author["display_name"])

        topics = [
            topic.get("display_name", "")
            for topic in item.get("topics") or []
            if isinstance(topic, dict)
        ]
        raw_license = clean_text(location.get("license"), 100)
        license_label = cls._license_label(raw_license)
        access = "creative_commons" if raw_license.lower().startswith("cc-") else "open_access"
        openalex_id = openalex_url.rsplit("/", 1)[-1]
        raw_type = clean_text(item.get("type"), 50).lower()
        resource_type = "book" if raw_type in {"book", "book-chapter"} else "article"
        raw = {
            "id": f"openalex:{openalex_id}",
            "title": item.get("title", ""),
            "authors": authors,
            "language": item.get("language") or "und",
            "year": item.get("publication_year"),
            "publisher": (location.get("source") or {}).get("display_name", "") if isinstance(location.get("source"), dict) else "",
            "isbn": [],
            "doi": doi,
            "subjects": topics,
            "source": cls.name,
            "source_url": source_url,
            "cover_url": "",
            "formats": formats,
            "access": access,
            "license": license_label,
            "verified_legal": is_oa and bool(source_url),
            "resource_type": resource_type,
            "identifiers": {"source_id": openalex_id, "openalex_id": openalex_id},
        }
        return clean_record(raw)

    @staticmethod
    def _license_label(value: str) -> str:
        normalized = normalize_text(value).replace(" ", "-")
        if normalized.startswith("cc-"):
            return normalized.upper().replace("-", " ")
        return value or "Open Access; license not reported by OpenAlex"
