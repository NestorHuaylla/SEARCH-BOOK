from xml.etree import ElementTree

import pytest

from scripts.providers.free_programming_books import FreeProgrammingBooksProvider
from scripts.providers.gutenberg import GutenbergProvider
from scripts.providers.internetarchive import InternetArchiveProvider
from scripts.providers.openalex import OpenAlexProvider
from scripts.providers.openlibrary import OpenLibraryProvider
from scripts.providers.openstax import OpenStaxProvider
from scripts.providers.standardebooks import StandardEbooksProvider


def test_free_programming_books_parser_skips_index_and_extracts_format():
    markdown = """
### Index
* [Python](#python)
### Python
* [Aprende Python](https://example.org/python) - Ada Pérez [(PDF)](https://example.org/python.pdf) (CC BY 4.0)
"""
    records = FreeProgrammingBooksProvider.parse_markdown(markdown, language="es")
    assert len(records) == 1
    assert records[0]["title"] == "Aprende Python"
    assert records[0]["access"] == "creative_commons"
    assert records[0]["authors"] == ["Ada Pérez"]
    assert records[0]["formats"] == [{"type": "pdf", "url": "https://example.org/python.pdf"}]


def test_gutenberg_parser_uses_only_supported_formats():
    record = GutenbergProvider.parse_book(
        {
            "id": 42,
            "title": "A legal classic",
            "authors": [{"name": "Doe, Jane"}],
            "languages": ["en"],
            "copyright": False,
            "subjects": ["Fiction"],
            "bookshelves": ["Classics"],
            "formats": {
                "application/epub+zip": "https://example.org/42.epub",
                "image/jpeg": "https://example.org/42.jpg",
                "application/octet-stream": "https://example.org/42.zip",
            },
        }
    )
    assert record["access"] == "public_domain"
    assert record["formats"] == [{"type": "epub", "url": "https://example.org/42.epub"}]
    assert record["cover_url"] == "https://example.org/42.jpg"


def test_gutenberg_parser_does_not_expose_uncertain_copyright_files():
    record = GutenbergProvider.parse_book(
        {
            "id": 43,
            "title": "Uncertain work",
            "authors": [],
            "languages": ["en"],
            "copyright": None,
            "formats": {"application/pdf": "https://example.org/43.pdf"},
        }
    )
    assert record["access"] == "metadata_only"
    assert record["formats"] == []


@pytest.mark.parametrize(
    ("ebook_access", "availability", "expected"),
    [
        ("public", {}, "open_access"),
        ("borrowable", {}, "digital_lending"),
        ("no_ebook", {"is_previewable": True}, "preview"),
        ("no_ebook", {}, "metadata_only"),
    ],
)
def test_openlibrary_access_classification(ebook_access, availability, expected):
    record = OpenLibraryProvider.parse_doc(
        {
            "key": "/works/OL1W",
            "title": "Book",
            "author_name": ["Author"],
            "language": ["spa"],
            "ebook_access": ebook_access,
            "availability": availability,
            "ia": ["archive-id"],
        }
    )
    assert record["access"] == expected
    assert bool(record["formats"]) is (expected == "open_access")


def test_openstax_parser_uses_explicit_license_and_official_pdf():
    record = OpenStaxProvider.parse_book(
        {
            "id": 7,
            "slug": "books/calculus",
            "title": "Calculus",
            "subjects": ["Math"],
            "pdf_url": "https://assets.openstax.org/calculus.pdf",
        },
        {
            "book_uuid": "uuid-7",
            "title": "Calculus",
            "publish_date": "2024-01-02",
            "authors": [{"value": {"name": "Open Author"}}],
            "license_name": "CC BY",
            "license_version": "4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "pdf_url": "https://assets.openstax.org/calculus.pdf",
            "meta": {"locale": "en"},
        },
    )
    assert record["access"] == "creative_commons"
    assert record["authors"] == ["Open Author"]
    assert record["formats"][0]["type"] == "pdf"


def test_standard_ebooks_atom_parser():
    entry = ElementTree.fromstring(
        """<entry xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">
          <id>https://standardebooks.org/ebooks/jane-doe/example</id><title>Example</title>
          <author><name>Jane Doe</name></author><published>2025-01-01T00:00:00Z</published>
          <rights>Public domain in the United States. CC0 1.0.</rights>
          <category term="Fiction"/><media:thumbnail url="https://example.org/cover.jpg"/>
          <link href="https://standardebooks.org/ebooks/jane-doe/example" rel="alternate" type="application/xhtml+xml"/>
          <link href="https://example.org/example.epub" rel="enclosure" type="application/epub+zip"/>
        </entry>"""
    )
    record = StandardEbooksProvider.parse_entry(entry)
    assert record["access"] == "public_domain"
    assert record["authors"] == ["Jane Doe"]
    assert record["formats"][0]["type"] == "epub"


def test_openalex_parser_requires_confirmed_oa_for_pdf():
    item = {
        "id": "https://openalex.org/W1",
        "doi": "https://doi.org/10.1000/open",
        "title": "Open paper",
        "publication_year": 2025,
        "language": "en",
        "type": "article",
        "authorships": [{"author": {"display_name": "Jane Doe"}}],
        "topics": [{"display_name": "Algorithms"}],
        "open_access": {"is_oa": True},
        "best_oa_location": {
            "is_oa": True,
            "license": "cc-by",
            "landing_page_url": "https://journal.example/article",
            "pdf_url": "https://journal.example/article.pdf",
        },
    }
    record = OpenAlexProvider.parse_work(item)
    assert record["verified_legal"] is True
    assert record["access"] == "creative_commons"
    assert record["formats"] == [{"type": "pdf", "url": "https://journal.example/article.pdf"}]
    item["best_oa_location"]["is_oa"] = False
    assert OpenAlexProvider.parse_work(item)["formats"] == []


def test_internet_archive_parser_never_invents_download_url():
    record = InternetArchiveProvider.parse_doc(
        {
            "identifier": "legal-item",
            "title": "Legal item",
            "creator": "Author",
            "language": "spa",
            "licenseurl": "https://creativecommons.org/licenses/by/4.0/",
        }
    )
    assert record["access"] == "creative_commons"
    assert record["formats"] == []
    assert record["source_url"] == "https://archive.org/details/legal-item"
