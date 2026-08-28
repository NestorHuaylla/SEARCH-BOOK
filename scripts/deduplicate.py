"""Work-level deduplication while retaining every legal provider."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any, Iterable

from scripts.normalize import clean_record, normalize_text, provider_snapshot, unique_strings


ACCESS_SCORE = {
    "public_domain": 90,
    "creative_commons": 85,
    "open_access": 80,
    "author_free": 70,
    "digital_lending": 45,
    "preview": 25,
    "metadata_only": 10,
    "unknown": 0,
}

SOURCE_SCORE = {
    "OpenStax": 20,
    "OAPEN Library": 20,
    "DOAB": 19,
    "Standard Ebooks": 20,
    "Project Gutenberg": 18,
    "OpenAlex": 16,
    "Open Library": 14,
    "Free Programming Books": 12,
    "Internet Archive": 10,
}


class DisjointSet:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        root_left, root_right = self.find(left), self.find(right)
        if root_left == root_right:
            return
        if self.rank[root_left] < self.rank[root_right]:
            root_left, root_right = root_right, root_left
        self.parent[root_right] = root_left
        if self.rank[root_left] == self.rank[root_right]:
            self.rank[root_left] += 1


def deduplicate(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = [clean_record(record) for record in records]
    cleaned = [record for record in cleaned if record["title"] and record["source_url"]]
    if not cleaned:
        return []

    groups = DisjointSet(len(cleaned))
    populated: list[dict[str, int]] = [{} for _ in range(6)]

    for index, record in enumerate(cleaned):
        for priority, key in identity_keys(record):
            existing = populated[priority].get(key)
            if existing is not None:
                groups.union(index, existing)
            else:
                populated[priority][key] = index

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, record in enumerate(cleaned):
        grouped[groups.find(index)].append(record)

    merged = [merge_group(group) for group in grouped.values()]
    return sorted(merged, key=lambda item: (normalize_text(item["title"]), item["id"]))


def identity_keys(record: dict[str, Any]) -> list[tuple[int, str]]:
    """Return keys in the requested strength order.

    Distinct priority registries prevent, for example, an ISBN from colliding
    with a DOI that happens to contain the same characters.
    """

    keys: list[tuple[int, str]] = []
    language = record.get("language", "und")
    language_suffix = f"|lang:{language}"
    for isbn in record.get("isbn", []):
        keys.append((0, f"{isbn}{language_suffix}"))
    if record.get("doi"):
        keys.append((1, f"{record['doi']}{language_suffix}"))
    openlibrary_id = record.get("identifiers", {}).get("openlibrary_work", "")
    if openlibrary_id:
        keys.append((2, f"{normalize_text(openlibrary_id)}{language_suffix}"))

    title = normalize_text(record.get("title"))
    authors = sorted(normalize_text(author) for author in record.get("authors", []) if normalize_text(author))
    if len(title) >= 4 and authors:
        keys.append((3, f"{title}|{'|'.join(authors[:3])}{language_suffix}"))

    edition = normalize_text(record.get("identifiers", {}).get("edition", ""))
    year = record.get("year")
    if title and edition and year:
        keys.append((4, f"{title}|{edition}|{year}{language_suffix}"))

    source_id = record.get("identifiers", {}).get("source_id", "")
    if source_id:
        keys.append((5, f"{normalize_text(record['source'])}|{normalize_text(source_id)}{language_suffix}"))
    return keys


def record_score(record: dict[str, Any]) -> int:
    score = ACCESS_SCORE.get(record.get("access", "unknown"), 0)
    score += SOURCE_SCORE.get(record.get("source", ""), 0)
    score += 5 if record.get("cover_url") else 0
    score += 4 if record.get("verified_legal") else 0
    score += min(len(record.get("formats", [])), 3) * 2
    score += min(len(record.get("subjects", [])), 5)
    score += 2 if record.get("isbn") else 0
    score += 2 if record.get("doi") else 0
    score += 3 if record.get("description") else 0
    return score


def merge_group(group: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(group, key=record_score, reverse=True)
    merged = dict(ordered[0])

    if not merged.get("subtitle"):
        merged["subtitle"] = next((record["subtitle"] for record in ordered if record.get("subtitle")), "")
    if not merged.get("description"):
        merged["description"] = next((record["description"] for record in ordered if record.get("description")), "")

    merged["authors"] = unique_strings(
        author for record in ordered for author in record.get("authors", [])
    )
    merged["isbn"] = list(
        dict.fromkeys(isbn for record in ordered for isbn in record.get("isbn", []))
    )
    merged["subjects"] = unique_strings(
        subject for record in ordered for subject in record.get("subjects", [])
    )

    identifiers: dict[str, str] = {}
    for record in ordered:
        for key, value in record.get("identifiers", {}).items():
            if key not in identifiers:
                identifiers[key] = value
            elif identifiers[key] != value:
                identifiers.setdefault(f"{normalize_text(record['source']).replace(' ', '_')}_{key}", value)
    merged["identifiers"] = identifiers

    providers: list[dict[str, Any]] = []
    provider_keys: set[tuple[str, str, str]] = set()
    for record in ordered:
        provider = provider_snapshot(record)
        key = (provider["source"], provider["source_id"], provider["source_url"])
        if key not in provider_keys:
            provider_keys.add(key)
            providers.append(provider)
    merged["providers"] = providers

    formats: list[dict[str, str]] = []
    seen_formats: set[tuple[str, str]] = set()
    for provider in providers:
        for item in provider["formats"]:
            key = (item["type"], item["url"])
            if key not in seen_formats:
                seen_formats.add(key)
                formats.append(item)
    merged["formats"] = formats
    merged["verified_legal"] = any(provider["verified_legal"] for provider in providers)

    stable_key = _stable_identity_key(merged)
    digest = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:24]
    merged["id"] = f"work:{digest}"
    return merged


def _stable_identity_key(record: dict[str, Any]) -> str:
    language_suffix = f"|lang:{record.get('language', 'und')}"
    if record.get("doi"):
        return f"doi:{record['doi']}{language_suffix}"
    if record.get("isbn"):
        return f"isbn:{sorted(record['isbn'])[0]}{language_suffix}"
    openlibrary_id = record.get("identifiers", {}).get("openlibrary_work")
    if openlibrary_id:
        return f"ol:{normalize_text(openlibrary_id)}{language_suffix}"
    authors = "|".join(sorted(normalize_text(author) for author in record.get("authors", [])))
    if authors:
        return f"text:{normalize_text(record['title'])}|{authors}{language_suffix}"
    # A title alone is not a safe work identity (many directories contain
    # distinct untitled/anonymous editions with the same display title).
    # Source + source_id is already the final deduplication key, so it is also
    # the collision-free fallback for the published stable id.
    source_id = normalize_text(record.get("identifiers", {}).get("source_id", ""))
    return f"source:{normalize_text(record.get('source'))}|{source_id}|{normalize_text(record['title'])}{language_suffix}"
