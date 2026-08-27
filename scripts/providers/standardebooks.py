"""Standard Ebooks provider using its public new-releases Atom feed."""

from __future__ import annotations

from typing import Any
from xml.etree import ElementTree

from scripts.normalize import clean_record, clean_text, normalize_text, safe_url
from scripts.providers.base import BaseProvider, ProviderError


class StandardEbooksProvider(BaseProvider):
    name = "Standard Ebooks"
    FEED_URL = "https://standardebooks.org/feeds/atom/new-releases"
    ATOM = "{http://www.w3.org/2005/Atom}"
    MEDIA = "{http://search.yahoo.com/mrss/}"
    MIME_FORMATS = {
        "application/epub+zip": "epub",
        "application/kepub+zip": "epub",
        "application/x-mobipocket-ebook": "azw3",
        "application/xhtml+xml": "html",
        "text/html": "html",
    }

    def fetch(self) -> list[dict[str, Any]]:
        response = self.get(self.FEED_URL, headers={"Accept": "application/atom+xml"})
        try:
            root = ElementTree.fromstring(response.content)
        except ElementTree.ParseError as exc:
            raise ProviderError(f"{self.name}: invalid Atom feed") from exc
        return [self.parse_entry(entry) for entry in root.findall(f"{self.ATOM}entry")]

    @classmethod
    def parse_entry(cls, entry: ElementTree.Element) -> dict[str, Any]:
        def text(tag: str) -> str:
            node = entry.find(f"{cls.ATOM}{tag}")
            return clean_text(node.text if node is not None else "")

        source_id = text("id")
        source_url = source_id
        authors = [
            clean_text(node.text)
            for node in entry.findall(f"{cls.ATOM}author/{cls.ATOM}name")
            if clean_text(node.text)
        ]
        subjects = [
            clean_text(node.attrib.get("term"))
            for node in entry.findall(f"{cls.ATOM}category")
            if clean_text(node.attrib.get("term"))
        ]
        cover = ""
        thumbnail = entry.find(f"{cls.MEDIA}thumbnail")
        if thumbnail is not None:
            cover = safe_url(thumbnail.attrib.get("url"))

        formats: list[dict[str, str]] = []
        for link in entry.findall(f"{cls.ATOM}link"):
            href = safe_url(link.attrib.get("href"))
            mime = clean_text(link.attrib.get("type"), 100).lower()
            relation = clean_text(link.attrib.get("rel"), 50).lower()
            if relation == "alternate" and href:
                source_url = href
            elif relation == "enclosure" and href and mime in cls.MIME_FORMATS:
                formats.append({"type": cls.MIME_FORMATS[mime], "url": href})

        rights = text("rights")
        normalized_rights = normalize_text(rights)
        if "public domain" in normalized_rights or "cc0" in normalized_rights:
            access = "public_domain"
            license_label = "Public domain / CC0 in the United States"
        elif "creative commons" in normalized_rights:
            access = "creative_commons"
            license_label = rights
        else:
            access = "author_free"
            license_label = rights or "See Standard Ebooks rights statement"

        raw = {
            "id": f"standardebooks:{source_id.rsplit('/', 1)[-1]}",
            "title": text("title"),
            "authors": authors,
            "language": "en",
            "year": text("published"),
            "publisher": cls.name,
            "isbn": [],
            "doi": "",
            "subjects": subjects,
            "source": cls.name,
            "source_url": source_url,
            "cover_url": cover,
            "formats": formats,
            "access": access,
            "license": license_label,
            "verified_legal": True,
            "resource_type": "book",
            "identifiers": {"source_id": source_id},
        }
        return clean_record(raw)

