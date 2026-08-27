import pytest

from scripts.normalize import (
    clean_record,
    clean_text,
    detect_language,
    normalize_doi,
    normalize_isbn,
    normalize_language,
    normalize_text,
    safe_url,
)


def test_text_normalization_strips_markup_controls_and_accents():
    assert clean_text(" <b>Métodos</b>\x00   numéricos ") == "Métodos numéricos"
    assert normalize_text("  MÉTODOS—Numéricos  ") == "metodos numericos"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Introducción a la programación para ciencia de datos", "es"),
        ("Introduction to computer programming and data science", "en"),
        ("Ada Lovelace", "und"),
    ],
)
def test_language_detection(text, expected):
    assert detect_language(text) == expected


def test_language_code_normalization():
    assert normalize_language("spa") == "es"
    assert normalize_language("en-US") == "en"
    assert normalize_language("not-a-code") == "und"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("978-0-306-40615-7", "9780306406157"),
        ("0-306-40615-2", "0306406152"),
        ("9780306406158", ""),
        ("not-an-isbn", ""),
    ],
)
def test_isbn_validation(value, expected):
    assert normalize_isbn(value) == expected


def test_doi_normalization():
    assert normalize_doi("https://doi.org/10.1000/ABC.123") == "10.1000/abc.123"
    assert normalize_doi("not a doi") == ""


@pytest.mark.parametrize(
    "value",
    ["javascript:alert(1)", "data:text/html,boom", "file:///etc/passwd", "https://user:pass@example.org/x"],
)
def test_url_validation_rejects_dangerous_values(value):
    assert safe_url(value) == ""


def test_url_validation_accepts_http_and_removes_fragments():
    assert safe_url("https://example.org/book?q=1#chapter") == "https://example.org/book?q=1"
    assert safe_url("http://example.org/book") == "http://example.org/book"


def test_unverified_record_cannot_expose_downloads():
    record = clean_record(
        {
            "id": "source:1",
            "title": "A book",
            "source": "Source",
            "source_url": "https://example.org/book",
            "formats": [{"type": "pdf", "url": "https://example.org/book.pdf"}],
            "access": "open_access",
            "verified_legal": False,
            "identifiers": {"source_id": "1"},
        }
    )
    assert record["formats"] == []


def test_string_false_cannot_authorize_downloads():
    record = clean_record(
        {
            "id": "source:false-string",
            "title": "Not verified",
            "source": "Source",
            "source_url": "https://example.org/not-verified",
            "formats": [{"type": "pdf", "url": "https://example.org/not-verified.pdf"}],
            "access": "open_access",
            "verified_legal": "false",
            "identifiers": {"source_id": "false-string"},
        }
    )
    assert record["verified_legal"] is False
    assert record["formats"] == []


def test_record_cleans_optional_search_description():
    record = clean_record(
        {
            "id": "source:2",
            "title": "A described book",
            "subtitle": "<b>Practical guide</b>",
            "description": "A summary with <script>markup</script> and useful details.",
            "source": "Source",
            "source_url": "https://example.org/book-2",
            "identifiers": {"source_id": "2"},
        }
    )
    assert record["subtitle"] == "Practical guide"
    assert record["description"] == "A summary with markup and useful details."
