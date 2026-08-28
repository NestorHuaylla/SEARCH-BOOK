from scripts.deduplicate import deduplicate


def test_same_title_without_authors_keeps_distinct_stable_ids():
    base = {
        "title": "Editorial",
        "authors": [],
        "language": "en",
        "year": 2025,
        "publisher": "",
        "isbn": [],
        "doi": "",
        "subjects": [],
        "source": "Directory",
        "source_url": "https://example.org/book",
        "cover_url": "",
        "formats": [],
        "access": "open_access",
        "license": "Open Access",
        "verified_legal": True,
        "resource_type": "book",
    }
    records = deduplicate([
        {**base, "id": "directory:1", "identifiers": {"source_id": "1"}},
        {
            **base,
            "id": "directory:2",
            "source_url": "https://example.org/book-2",
            "identifiers": {"source_id": "2"},
        },
    ])
    assert len(records) == 2
    assert len({record["id"] for record in records}) == 2


def record(source, source_id, *, title="Métodos numéricos", authors=None, isbn=None, doi=""):
    return {
        "id": f"{source}:{source_id}",
        "title": title,
        "authors": authors if authors is not None else ["Ana Pérez"],
        "language": "es",
        "year": 2020,
        "publisher": "Universidad",
        "isbn": isbn or [],
        "doi": doi,
        "subjects": ["Matemáticas"],
        "source": source,
        "source_url": f"https://example.org/{source_id}",
        "cover_url": "",
        "formats": [{"type": "pdf", "url": f"https://example.org/{source_id}.pdf"}],
        "access": "open_access",
        "license": "CC BY 4.0",
        "verified_legal": True,
        "resource_type": "book",
        "identifiers": {"source_id": source_id},
    }


def test_deduplicates_by_isbn_and_keeps_providers():
    books = deduplicate(
        [
            record("Source A", "a", isbn=["9780306406157"]),
            record("Source B", "b", isbn=["978-0-306-40615-7"]),
        ]
    )
    assert len(books) == 1
    assert {provider["source"] for provider in books[0]["providers"]} == {"Source A", "Source B"}
    assert len(books[0]["formats"]) == 2


def test_does_not_merge_records_declared_in_different_languages():
    spanish = record("Source A", "es")
    spanish["language"] = "es"
    english = record("Source B", "en")
    english["language"] = "en"

    books = deduplicate([spanish, english])

    assert len(books) == 2
    assert {book["language"] for book in books} == {"es", "en"}


def test_deduplicates_by_doi():
    books = deduplicate(
        [record("A", "1", doi="10.1000/example"), record("B", "2", doi="https://doi.org/10.1000/example")]
    )
    assert len(books) == 1


def test_deduplicates_accent_insensitive_title_and_author():
    books = deduplicate(
        [
            record("A", "1", title="Métodos Numéricos", authors=["Ana Pérez"]),
            record("B", "2", title="metodos numericos", authors=["Ana Perez"]),
        ]
    )
    assert len(books) == 1


def test_does_not_merge_weak_titles_without_authors():
    books = deduplicate(
        [record("A", "1", title="Manual", authors=[]), record("B", "2", title="Manual", authors=[])]
    )
    assert len(books) == 2
