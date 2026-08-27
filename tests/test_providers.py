from typing import Any

from scripts.config import Settings
from scripts.deduplicate import deduplicate
from scripts.providers.base import BaseProvider
from scripts.providers.gutenberg import GutenbergProvider
from scripts.update_books import load_json, synchronize


class StubResponse:
    def __init__(self, payload: Any):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class StubSession:
    def __init__(self, payload: Any):
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return StubResponse(self.payload)


def test_provider_fetch_uses_mock_without_network(monkeypatch):
    monkeypatch.setenv("OPENBOOK_GUTENBERG_MAX_PAGES", "1")
    payload = {
        "next": None,
        "results": [
            {
                "id": 1,
                "title": "Mock book",
                "authors": [{"name": "Mock Author"}],
                "languages": ["en"],
                "copyright": False,
                "subjects": [],
                "bookshelves": [],
                "formats": {"text/html": "https://example.org/read"},
            }
        ],
    }
    session = StubSession(payload)
    books = GutenbergProvider(settings=Settings(), session=session).fetch()
    assert len(books) == 1
    assert books[0]["title"] == "Mock book"
    assert session.calls[0][0] == GutenbergProvider.API_URL


class AlwaysFailsProvider(BaseProvider):
    name = "Stable Source"

    def fetch(self):
        raise RuntimeError("temporary outage")


def test_failed_provider_retains_previous_snapshot():
    existing_books = deduplicate(
        [
            {
                "id": "stable:1",
                "title": "Retained book",
                "authors": ["Author"],
                "language": "en",
                "year": 2020,
                "publisher": "",
                "isbn": [],
                "doi": "",
                "subjects": [],
                "source": "Stable Source",
                "source_url": "https://example.org/book",
                "cover_url": "",
                "formats": [],
                "access": "metadata_only",
                "license": "",
                "verified_legal": False,
                "resource_type": "book",
                "identifiers": {"source_id": "1"},
            }
        ]
    )
    books, statuses = synchronize(
        [AlwaysFailsProvider],
        {"schema_version": 1, "books": existing_books},
        Settings(),
    )
    assert len(books) == 1
    assert books[0]["title"] == "Retained book"
    assert statuses["Stable Source"]["retained"] is True


def test_load_json_reads_file_and_uses_fallback(tmp_path):
    valid = tmp_path / "valid.json"
    valid.write_text('{"ok": true}', encoding="utf-8")
    assert load_json(valid, {}) == {"ok": True}
    assert load_json(tmp_path / "missing.json", {"fallback": True}) == {"fallback": True}
