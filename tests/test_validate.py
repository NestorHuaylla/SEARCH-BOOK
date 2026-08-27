import pytest

from scripts.deduplicate import deduplicate
from scripts.validate import CatalogValidationError, validate_catalog


def valid_catalog():
    books = deduplicate(
        [
            {
                "id": "source:1",
                "title": "Valid book",
                "authors": ["Author"],
                "language": "en",
                "year": 2024,
                "publisher": "Publisher",
                "isbn": [],
                "doi": "",
                "subjects": ["Testing"],
                "source": "Source",
                "source_url": "https://example.org/book",
                "cover_url": "",
                "formats": [{"type": "pdf", "url": "https://example.org/book.pdf"}],
                "access": "open_access",
                "license": "CC BY 4.0",
                "verified_legal": True,
                "resource_type": "book",
                "identifiers": {"source_id": "1"},
            }
        ]
    )
    return {"schema_version": 1, "generated_at": "2026-01-01T00:00:00Z", "books": books}


def test_valid_catalog_passes():
    validate_catalog(valid_catalog())


def test_duplicate_ids_fail():
    catalog = valid_catalog()
    catalog["books"].append(dict(catalog["books"][0]))
    with pytest.raises(CatalogValidationError, match="duplicate id"):
        validate_catalog(catalog)

