"""Normalization and security rules shared by every provider."""

from __future__ import annotations

import html
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from scripts.models import ACCESS_TYPES, FORMAT_TYPES, RESOURCE_TYPES, empty_record


CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
TAG_RE = re.compile(r"<[^>]*>")
SPACE_RE = re.compile(r"\s+")
NON_WORD_RE = re.compile(r"[^\w]+", re.UNICODE)
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)

LANGUAGE_MAP = {
    "ara": "ar",
    "ar": "ar",
    "deu": "de",
    "ger": "de",
    "de": "de",
    "eng": "en",
    "en": "en",
    "esl": "es",
    "spa": "es",
    "es": "es",
    "fra": "fr",
    "fre": "fr",
    "fr": "fr",
    "ita": "it",
    "it": "it",
    "jpn": "ja",
    "ja": "ja",
    "lat": "la",
    "la": "la",
    "pol": "pl",
    "pl": "pl",
    "por": "pt",
    "pt": "pt",
    "rus": "ru",
    "ru": "ru",
    "zho": "zh",
    "chi": "zh",
    "zh": "zh",
    "und": "und",
}

SPANISH_HINTS = {
    "algoritmos",
    "ciencia",
    "datos",
    "desarrollo",
    "español",
    "fundamentos",
    "introducción",
    "libro",
    "métodos",
    "para",
    "programación",
}
ENGLISH_HINTS = {
    "algorithms",
    "book",
    "computer",
    "data",
    "development",
    "for",
    "introduction",
    "methods",
    "programming",
    "science",
}


def clean_text(value: Any, max_length: int = 500) -> str:
    """Convert external text to a compact, tag-free Unicode string."""

    if value is None:
        return ""
    text = html.unescape(str(value))
    text = TAG_RE.sub(" ", text)
    text = CONTROL_RE.sub("", text)
    text = SPACE_RE.sub(" ", text).strip()
    return text[:max_length]


def normalize_text(value: Any) -> str:
    """Normalize text for matching while preserving letters and numbers."""

    text = clean_text(value, max_length=10_000).casefold()
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return SPACE_RE.sub(" ", NON_WORD_RE.sub(" ", without_marks)).strip()


def unique_strings(values: Iterable[Any], *, max_items: int = 80) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = clean_text(value)
        key = normalize_text(cleaned)
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
        if len(result) >= max_items:
            break
    return result


def normalize_language(value: Any) -> str:
    raw = clean_text(value, 20).lower().replace("_", "-")
    primary = raw.split("-", 1)[0]
    return LANGUAGE_MAP.get(primary, primary if len(primary) == 2 and primary.isalpha() else "und")


def detect_language(text: Any) -> str:
    """Small deterministic fallback; providers should prefer explicit metadata."""

    normalized = normalize_text(text)
    tokens = set(normalized.split())
    if not tokens:
        return "und"
    es_score = len(tokens & {normalize_text(item) for item in SPANISH_HINTS})
    en_score = len(tokens & ENGLISH_HINTS)
    if es_score > en_score and es_score:
        return "es"
    if en_score > es_score and en_score:
        return "en"
    return "und"


def normalize_isbn(value: Any) -> str:
    raw = re.sub(r"[^0-9Xx]", "", clean_text(value, 40)).upper()
    if len(raw) == 10 and _valid_isbn10(raw):
        return raw
    if len(raw) == 13 and _valid_isbn13(raw):
        return raw
    return ""


def _valid_isbn10(value: str) -> bool:
    if not re.fullmatch(r"\d{9}[\dX]", value):
        return False
    total = sum((10 - index) * (10 if char == "X" else int(char)) for index, char in enumerate(value))
    return total % 11 == 0


def _valid_isbn13(value: str) -> bool:
    if not value.isdigit():
        return False
    total = sum(int(char) * (1 if index % 2 == 0 else 3) for index, char in enumerate(value[:12]))
    check = (10 - total % 10) % 10
    return check == int(value[-1])


def normalize_doi(value: Any) -> str:
    raw = clean_text(value, 300).strip().lower()
    raw = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", raw, flags=re.IGNORECASE)
    raw = raw.rstrip(".,; ")
    return raw if DOI_RE.fullmatch(raw) else ""


def safe_url(value: Any) -> str:
    """Return an absolute HTTP(S) URL without credentials, or an empty string."""

    raw = clean_text(value, 2_000)
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return ""
    if parts.username or parts.password:
        return ""
    if any(char.isspace() for char in parts.netloc):
        return ""
    scheme = parts.scheme.lower()
    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, ""))


def normalize_year(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    match = re.search(r"(?<!\d)(\d{3,4})(?!\d)", str(value))
    if not match:
        return None
    year = int(match.group(1))
    max_year = datetime.now(UTC).year + 1
    return year if 100 <= year <= max_year else None


def normalize_format(item: Any) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None
    format_type = clean_text(item.get("type"), 30).lower()
    url = safe_url(item.get("url"))
    if format_type not in FORMAT_TYPES or not url:
        return None
    return {"type": format_type, "url": url}


def clean_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a complete, safe record and enforce legal-download invariants."""

    source = clean_text(raw.get("source"), 100) or "Unknown"
    identifiers_raw = raw.get("identifiers") if isinstance(raw.get("identifiers"), dict) else {}
    source_id = clean_text(identifiers_raw.get("source_id") or raw.get("id"), 300)
    record = empty_record(source=source, source_id=source_id, title=clean_text(raw.get("title"), 500))

    record["id"] = clean_text(raw.get("id"), 400) or record["id"]
    record["subtitle"] = clean_text(raw.get("subtitle"), 500)
    record["description"] = clean_text(raw.get("description"), 4_000)
    record["authors"] = unique_strings(raw.get("authors") or [], max_items=30)
    record["subjects"] = unique_strings(raw.get("subjects") or [], max_items=80)
    record["language"] = normalize_language(raw.get("language"))
    if record["language"] == "und":
        record["language"] = detect_language(" ".join([record["title"], *record["subjects"]]))
    record["year"] = normalize_year(raw.get("year"))
    record["publisher"] = clean_text(raw.get("publisher"), 300)
    record["isbn"] = list(
        dict.fromkeys(
            isbn for value in (raw.get("isbn") or []) if (isbn := normalize_isbn(value))
        )
    )
    record["doi"] = normalize_doi(raw.get("doi"))
    record["source_url"] = safe_url(raw.get("source_url"))
    record["cover_url"] = safe_url(raw.get("cover_url"))

    access = clean_text(raw.get("access"), 40).lower()
    record["access"] = access if access in ACCESS_TYPES else "unknown"
    record["license"] = clean_text(raw.get("license"), 200)
    record["verified_legal"] = raw.get("verified_legal") is True
    resource_type = clean_text(raw.get("resource_type"), 30).lower()
    record["resource_type"] = resource_type if resource_type in RESOURCE_TYPES else "other"

    identifiers: dict[str, str] = {"source_id": source_id}
    for key, value in identifiers_raw.items():
        clean_key = normalize_text(key).replace(" ", "_")[:60]
        clean_value = clean_text(value, 400)
        if clean_key and clean_value:
            identifiers[clean_key] = clean_value
    record["identifiers"] = identifiers

    formats: list[dict[str, str]] = []
    seen_formats: set[tuple[str, str]] = set()
    for item in raw.get("formats") or []:
        normalized = normalize_format(item)
        if normalized:
            key = (normalized["type"], normalized["url"])
            if key not in seen_formats:
                seen_formats.add(key)
                formats.append(normalized)

    if not record["verified_legal"] or record["access"] in {"metadata_only", "unknown"}:
        formats = []
    record["formats"] = formats
    return record


def provider_snapshot(record: dict[str, Any]) -> dict[str, Any]:
    """Extract provider-specific access details for a deduplicated work."""

    return {
        "source": record["source"],
        "source_id": record.get("identifiers", {}).get("source_id", ""),
        "source_url": record["source_url"],
        "language": record["language"],
        "formats": record["formats"],
        "access": record["access"],
        "license": record["license"],
        "verified_legal": record["verified_legal"],
    }
