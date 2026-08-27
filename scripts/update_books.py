"""Synchronize providers, deduplicate records and publish static catalog files."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import SCHEMA_VERSION
from scripts.config import DATA_DIR, SHARDS_DIR, Settings
from scripts.deduplicate import deduplicate
from scripts.providers.base import BaseProvider
from scripts.providers.free_programming_books import FreeProgrammingBooksProvider
from scripts.providers.gutenberg import GutenbergProvider
from scripts.providers.internetarchive import InternetArchiveProvider
from scripts.providers.openalex import OpenAlexProvider
from scripts.providers.openlibrary import OpenLibraryProvider
from scripts.providers.openstax import OpenStaxProvider
from scripts.providers.standardebooks import StandardEbooksProvider
from scripts.validate import validate_catalog


LOGGER = logging.getLogger("openbook.sync")

PROVIDER_TYPES: tuple[type[BaseProvider], ...] = (
    FreeProgrammingBooksProvider,
    GutenbergProvider,
    OpenLibraryProvider,
    OpenStaxProvider,
    StandardEbooksProvider,
    OpenAlexProvider,
    InternetArchiveProvider,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        action="append",
        default=[],
        help="Run only a provider name (repeatable, case-insensitive). Others are retained.",
    )
    parser.add_argument("--list-providers", action="store_true", help="List provider names and exit.")
    return parser.parse_args(argv)


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("Could not read %s: %s", path, exc)
        return fallback


def load_existing_catalog(settings: Settings) -> dict[str, Any]:
    catalog = load_json(DATA_DIR / "books.json", {"schema_version": SCHEMA_VERSION, "books": []})
    if catalog.get("books") or not catalog.get("partitioned"):
        return catalog
    metadata = load_json(DATA_DIR / "metadata.json", {})
    books: list[dict[str, Any]] = []
    for entry in metadata.get("shards", []):
        if not isinstance(entry, dict) or not entry.get("path"):
            continue
        payload = load_json(settings.root_dir / entry["path"], [])
        if not isinstance(payload, list):
            raise ValueError(f"Invalid catalog shard: {entry['path']}")
        books.extend(payload)
    if len(books) != catalog.get("total_records", len(books)):
        raise ValueError("Partitioned catalog is incomplete; refusing to replace provider snapshots")
    return {"schema_version": SCHEMA_VERSION, "generated_at": catalog.get("generated_at"), "books": books}


def extract_provider_records(catalog: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Recreate provider records from merged works for failure-safe updates."""

    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for book in catalog.get("books", []):
        providers = book.get("providers") or []
        if not providers and book.get("source"):
            providers = [
                {
                    "source": book["source"],
                    "source_id": book.get("identifiers", {}).get("source_id", ""),
                    "source_url": book.get("source_url", ""),
                    "formats": book.get("formats", []),
                    "access": book.get("access", "unknown"),
                    "license": book.get("license", ""),
                    "verified_legal": book.get("verified_legal", False),
                }
            ]
        for provider in providers:
            source = provider.get("source", "")
            if not source:
                continue
            record = {
                key: book.get(key)
                for key in (
                    "title",
                    "subtitle",
                    "description",
                    "authors",
                    "language",
                    "year",
                    "publisher",
                    "isbn",
                    "doi",
                    "subjects",
                    "cover_url",
                    "resource_type",
                )
            }
            record.update(
                {
                    "id": f"retained:{source}:{provider.get('source_id', '')}",
                    "source": source,
                    "source_url": provider.get("source_url", ""),
                    "formats": provider.get("formats", []),
                    "access": provider.get("access", "unknown"),
                    "license": provider.get("license", ""),
                    "verified_legal": provider.get("verified_legal", False),
                    "identifiers": {
                        **book.get("identifiers", {}),
                        "source_id": provider.get("source_id", ""),
                    },
                }
            )
            record["language"] = provider.get("language") or book.get("language", "und")
            by_source[source].append(record)
    return by_source


def choose_providers(names: Iterable[str]) -> list[type[BaseProvider]]:
    requested = {name.casefold().strip() for name in names if name.strip()}
    if not requested:
        return list(PROVIDER_TYPES)
    selected = [provider for provider in PROVIDER_TYPES if provider.name.casefold() in requested]
    known = {provider.name.casefold() for provider in selected}
    missing = sorted(requested - known)
    if missing:
        choices = ", ".join(provider.name for provider in PROVIDER_TYPES)
        raise SystemExit(f"Unknown provider(s): {', '.join(missing)}. Available: {choices}")
    return selected


def synchronize(
    provider_types: Iterable[type[BaseProvider]],
    existing: dict[str, Any],
    settings: Settings,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    records_by_source = extract_provider_records(existing)
    statuses: dict[str, dict[str, Any]] = {}

    for provider_type in provider_types:
        provider = provider_type(settings=settings)
        previous = records_by_source.get(provider.name, [])
        try:
            records = provider.fetch()
            if not records and previous:
                raise ValueError("provider returned zero records; retaining previous snapshot")
            records_by_source[provider.name] = records
            statuses[provider.name] = {"status": "ok", "records": len(records), "retained": False}
            LOGGER.info("%-28s OK (%d records)", provider.name, len(records))
        except Exception as exc:  # provider isolation is an explicit design requirement
            statuses[provider.name] = {
                "status": "error",
                "records": len(previous),
                "retained": bool(previous),
                "error": str(exc)[:500],
            }
            LOGGER.error("%-28s ERROR (%s); retained=%d", provider.name, exc, len(previous))

    all_records = [record for records in records_by_source.values() for record in records]
    return deduplicate(all_records), statuses


def json_bytes(value: Any, *, compact: bool = False) -> bytes:
    options = {"ensure_ascii": False, "sort_keys": False}
    if compact:
        options["separators"] = (",", ":")
    else:
        options["indent"] = 2
    return (json.dumps(value, **options) + "\n").encode("utf-8")


def atomic_write(path: Path, value: Any, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json_bytes(value, compact=compact)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temp_path = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def catalog_hash(books: list[dict[str, Any]]) -> str:
    compact = json.dumps(books, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def publish_catalog(
    books: list[dict[str, Any]],
    statuses: dict[str, dict[str, Any]],
    settings: Settings,
    existing: dict[str, Any],
) -> bool:
    old_books = existing.get("books", [])
    old_hash = catalog_hash(old_books)
    new_hash = catalog_hash(books)
    metadata_path = DATA_DIR / "metadata.json"
    existing_metadata = load_json(metadata_path, {})
    expected_shards = existing_metadata.get("shards", [])
    shards_exist = all(
        (settings.root_dir / item["path"]).exists()
        for item in expected_shards
        if isinstance(item, dict) and item.get("path")
    ) if expected_shards else not books
    if old_hash == new_hash and metadata_path.exists() and shards_exist:
        LOGGER.info("Catalog unchanged (%d works); files were not rewritten", len(books))
        return False

    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    full_catalog = {"schema_version": SCHEMA_VERSION, "generated_at": generated_at, "books": books}
    validate_catalog(full_catalog)

    SHARDS_DIR.mkdir(parents=True, exist_ok=True)
    for stale in SHARDS_DIR.glob("books-*.json"):
        stale.unlink()

    shard_manifest: list[dict[str, Any]] = []
    for start in range(0, len(books), settings.shard_size):
        number = start // settings.shard_size
        chunk = books[start : start + settings.shard_size]
        relative_path = f"data/shards/books-{number:04d}.json"
        shard_path = settings.root_dir / relative_path
        atomic_write(shard_path, chunk, compact=True)
        shard_manifest.append(
            {"path": relative_path, "records": len(chunk), "bytes": shard_path.stat().st_size}
        )

    provider_counts: dict[str, int] = defaultdict(int)
    for book in books:
        for provider in book.get("providers", []):
            provider_counts[provider["source"]] += 1

    metadata = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "total_records": len(books),
        "catalog_sha256": new_hash,
        "providers": {
            source: {"records": count, **statuses.get(source, {"status": "retained", "retained": True})}
            for source, count in sorted(provider_counts.items())
        },
        "shards": shard_manifest,
    }
    partitioned = len(books) > settings.inline_catalog_limit
    published_catalog = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "books": [] if partitioned else books,
        "partitioned": partitioned,
        "total_records": len(books),
    }
    atomic_write(DATA_DIR / "books.json", published_catalog)
    atomic_write(metadata_path, metadata)
    LOGGER.info("Published %d works in %d shard(s)", len(books), len(shard_manifest))
    return True


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.list_providers:
        for provider in PROVIDER_TYPES:
            print(provider.name)
        return 0

    settings = Settings()
    existing = load_existing_catalog(settings)
    providers = choose_providers(args.provider)
    LOGGER.info("Starting OpenBook Search sync with %d provider(s)", len(providers))
    books, statuses = synchronize(providers, existing, settings)
    publish_catalog(books, statuses, settings, existing)
    LOGGER.info("Synchronization complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
