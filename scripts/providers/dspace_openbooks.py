"""Shared parser for the official OAPEN and DOAB DSpace REST APIs."""

from __future__ import annotations

import os
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urljoin, urlsplit

from scripts.normalize import clean_record, clean_text, normalize_text, safe_url
from scripts.providers.base import BaseProvider, ProviderError


class DSpaceOpenBooksProvider(BaseProvider):
    """Synchronize a bounded, recent slice of an open-book directory."""

    base_url = ""
    limit_env = ""
    query_env = ""
    default_limit = 750
    default_query = "dc.type:book"
    # Expanded DSpace records are large; batches of 100 regularly exceed the
    # public endpoints' response timeout. Smaller pages are slower overall but
    # much more reliable and easier on the service.
    page_size = 25

    def fetch(self) -> list[dict[str, Any]]:
        limit = self._limit()
        query = os.getenv(self.query_env, self.default_query).strip() or self.default_query
        records: list[dict[str, Any]] = []
        seen: set[str] = set()
        offset = 0

        while len(records) < limit:
            requested = min(self.page_size, limit - len(records))
            payload = self.get_json(
                f"{self.base_url}/rest/search",
                params={
                    "query": query,
                    "expand": "metadata,bitstreams",
                    "limit": requested,
                    "offset": offset,
                    "sort": "dc.date.accessioned_dt",
                    "order": "DESC",
                },
                headers={"Accept": "application/json"},
            )
            if not isinstance(payload, list):
                raise ProviderError(f"{self.name}: unexpected REST search response")
            if not payload:
                break

            new_items = 0
            for item in payload:
                if not isinstance(item, dict):
                    continue
                source_id = clean_text(item.get("handle") or item.get("uuid"), 300)
                if not source_id or source_id in seen:
                    continue
                seen.add(source_id)
                new_items += 1
                record = self.parse_item(item)
                if record["title"] and record["source_url"]:
                    records.append(record)
            offset += len(payload)
            if len(payload) < requested:
                break
            if new_items == 0:
                raise ProviderError(f"{self.name}: REST pagination repeated the same records")
        return records

    def _limit(self) -> int:
        raw = os.getenv(self.limit_env, str(self.default_limit))
        try:
            return max(1, min(int(raw), 10_000))
        except ValueError as exc:
            raise ProviderError(f"{self.name}: {self.limit_env} must be an integer") from exc

    @classmethod
    def parse_item(cls, item: dict[str, Any]) -> dict[str, Any]:
        metadata = cls._metadata_map(item.get("metadata"))
        bitstreams = item.get("bitstreams") if isinstance(item.get("bitstreams"), list) else []
        handle = clean_text(item.get("handle") or item.get("uuid"), 300)

        def values(*keys: str) -> list[str]:
            return [value for key in keys for value in metadata.get(key, []) if value]

        title = next(iter(values("dc.title")), clean_text(item.get("name"), 500))
        subtitle = next(iter(values("dc.title.alternative")), "")
        authors = values("dc.contributor.author", "dc.creator")
        subjects = values("dc.subject", "dc.subject.other", "dc.subject.classification")
        description = next(iter(values("dc.description.abstract", "dc.description")), "")
        publisher = next(iter(values("publisher.name", "dc.publisher", "oapen.imprint")), "")
        language = next(iter(values("dc.language.iso", "dc.language")), "und")
        year = next(iter(values("dc.date.issued", "dc.date.created")), None)
        doi = next(iter(values("oapen.identifier.doi", "dc.identifier.doi")), "")
        isbn = values("dc.identifier.isbn", "oapen.identifier.isbn", "dc.identifier")
        source_url = next(iter(values("dc.identifier.uri")), "")
        source_url = safe_url(source_url) or f"{cls.base_url}/handle/{handle}"

        formats: list[dict[str, str]] = []
        cover_url = ""
        license_values = values("dc.rights", "dc.rights.uri", "dcterms.accessRights")
        download_urls = values("oapen.identifier.downloadUrl")

        for bitstream in bitstreams:
            if not isinstance(bitstream, dict):
                continue
            bundle = clean_text(bitstream.get("bundleName"), 40).upper()
            mime = clean_text(bitstream.get("mimeType"), 100).lower()
            name = clean_text(bitstream.get("name"), 500)
            retrieve = safe_url(bitstream.get("retrieveLink")) or safe_url(
                urljoin(f"{cls.base_url}/", str(bitstream.get("retrieveLink") or "").lstrip("/"))
            )
            bitstream_metadata = cls._metadata_map(bitstream.get("metadata"))
            download_urls.extend(bitstream_metadata.get("oapen.identifier.downloadUrl", []))
            license_values.extend(bitstream_metadata.get("dc.rights.uri", []))
            code = clean_text(bitstream.get("code"), 100)
            if code:
                license_values.append(code)

            if bundle == "THUMBNAIL" and mime.startswith("image/") and retrieve and not cover_url:
                cover_url = retrieve
            if bundle != "ORIGINAL" or not retrieve:
                continue
            format_type = cls._format_type(mime, name)
            if format_type:
                formats.append({"type": format_type, "url": retrieve})

        for raw_url in download_urls:
            url = safe_url(raw_url)
            if not url:
                continue
            format_type = cls._format_type("", PurePosixPath(urlsplit(url).path).name) or "read"
            formats.append({"type": format_type, "url": url})

        license_label = " · ".join(dict.fromkeys(filter(None, license_values)))[:200]
        normalized_license = normalize_text(license_label)
        access = "creative_commons" if any(
            marker in normalized_license for marker in ("creative commons", "creativecommons", "cc by")
        ) else "open_access"
        raw = {
            "id": f"{normalize_text(cls.name).replace(' ', '')}:{handle}",
            "title": title,
            "subtitle": subtitle,
            "description": description,
            "authors": authors,
            "language": language,
            "year": year,
            "publisher": publisher,
            "isbn": isbn,
            "doi": doi,
            "subjects": subjects,
            "source": cls.name,
            "source_url": source_url,
            "cover_url": cover_url,
            "formats": formats,
            "access": access,
            "license": license_label or "Open Access; see official item record",
            "verified_legal": True,
            "resource_type": "book",
            "identifiers": {
                "source_id": handle,
                "handle": handle,
                "dspace_uuid": clean_text(item.get("uuid"), 100),
            },
        }
        return clean_record(raw)

    @staticmethod
    def _metadata_map(raw: Any) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        if not isinstance(raw, list):
            return result
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            key = clean_text(entry.get("key"), 150)
            value = clean_text(entry.get("value"), 4_000)
            if key and value:
                result.setdefault(key, []).append(value)
        return result

    @staticmethod
    def _format_type(mime: str, name: str) -> str:
        normalized_mime = mime.split(";", 1)[0].strip().lower()
        suffix = PurePosixPath(name.lower()).suffix
        if normalized_mime == "application/pdf" or suffix == ".pdf":
            return "pdf"
        if normalized_mime == "application/epub+zip" or suffix == ".epub":
            return "epub"
        if normalized_mime == "text/html" or suffix in {".html", ".htm"}:
            return "html"
        if normalized_mime == "text/plain" or suffix == ".txt":
            return "text"
        return ""
