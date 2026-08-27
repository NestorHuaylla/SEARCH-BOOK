"""JSON Schema and semantic catalog validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from scripts.config import DATA_DIR, ROOT_DIR
from scripts.normalize import safe_url


SCHEMA_PATH = DATA_DIR / "schema.json"


class CatalogValidationError(ValueError):
    pass


def load_schema(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_catalog(catalog: dict[str, Any], schema_path: Path = SCHEMA_PATH) -> None:
    validator = Draft202012Validator(load_schema(schema_path), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(catalog), key=lambda item: list(item.absolute_path))
    messages = [f"{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}" for error in errors]

    seen_ids: set[str] = set()
    for index, book in enumerate(catalog.get("books", [])):
        book_id = book.get("id", "")
        if book_id in seen_ids:
            messages.append(f"books/{index}/id: duplicate id {book_id!r}")
        seen_ids.add(book_id)

        if not book.get("verified_legal") and book.get("formats"):
            messages.append(f"books/{index}/formats: unverified record exposes downloads")
        if book.get("access") in {"metadata_only", "unknown"} and book.get("formats"):
            messages.append(f"books/{index}/formats: metadata-only record exposes downloads")

        for field in ("source_url", "cover_url"):
            url = book.get(field, "")
            if url and not safe_url(url):
                messages.append(f"books/{index}/{field}: unsafe URL")
        for provider_index, provider in enumerate(book.get("providers", [])):
            if not provider.get("verified_legal") and provider.get("formats"):
                messages.append(
                    f"books/{index}/providers/{provider_index}/formats: unverified provider exposes downloads"
                )

    if messages:
        preview = "\n".join(f"- {message}" for message in messages[:30])
        suffix = f"\n... and {len(messages) - 30} more" if len(messages) > 30 else ""
        raise CatalogValidationError(f"Catalog validation failed:\n{preview}{suffix}")


def validate_file(path: Path) -> None:
    with path.open("r", encoding="utf-8") as handle:
        validate_catalog(json.load(handle))


def validate_published_catalog() -> None:
    with (DATA_DIR / "books.json").open("r", encoding="utf-8") as handle:
        catalog = json.load(handle)
    if not catalog.get("partitioned"):
        validate_catalog(catalog)
        return

    metadata_path = DATA_DIR / "metadata.json"
    with metadata_path.open("r", encoding="utf-8") as handle:
        metadata = json.load(handle)
    books: list[dict[str, Any]] = []
    for entry in metadata.get("shards", []):
        shard_path = ROOT_DIR / entry["path"]
        with shard_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, list):
            raise CatalogValidationError(f"Shard {entry['path']} is not an array")
        if len(payload) != entry.get("records"):
            raise CatalogValidationError(f"Shard {entry['path']} record count does not match metadata")
        books.extend(payload)
    if len(books) != catalog.get("total_records") or len(books) != metadata.get("total_records"):
        raise CatalogValidationError("Partitioned catalog total does not match its manifest")
    validate_catalog(
        {
            "schema_version": catalog["schema_version"],
            "generated_at": catalog["generated_at"],
            "books": books,
        }
    )


if __name__ == "__main__":
    validate_published_catalog()
    print("published catalog OK")
