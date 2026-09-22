"""Test per app.services.dedup: normalizzazione URL, hash contenuto, confronto campi."""

from __future__ import annotations

from app.services.dedup import compare_core_fields, content_sha256, normalize_url


def test_normalize_url_lowercases_host() -> None:
    assert normalize_url("https://WWW.Example.com/path") == normalize_url(
        "https://www.example.com/path"
    )


def test_normalize_url_strips_tracking_params() -> None:
    tracked = "https://example.com/ad/123?utm_source=fb&utm_campaign=x&id=123"
    clean = "https://example.com/ad/123?id=123"
    assert normalize_url(tracked) == normalize_url(clean)


def test_normalize_url_reorders_query_params() -> None:
    a = "https://example.com/ad?b=2&a=1"
    b = "https://example.com/ad?a=1&b=2"
    assert normalize_url(a) == normalize_url(b)


def test_normalize_url_strips_fragment_and_trailing_slash() -> None:
    a = "https://example.com/ad/123/#section"
    b = "https://example.com/ad/123"
    assert normalize_url(a) == normalize_url(b)


def test_normalize_url_different_paths_differ() -> None:
    a = normalize_url("https://example.com/ad/123")
    b = normalize_url("https://example.com/ad/456")
    assert a != b


def test_content_sha256_is_deterministic() -> None:
    text = "Titolo annuncio - descrizione di esempio"
    assert content_sha256(text) == content_sha256(text)


def test_content_sha256_differs_for_different_content() -> None:
    assert content_sha256("testo A") != content_sha256("testo B")


def test_content_sha256_is_hex_length_64() -> None:
    digest = content_sha256("qualsiasi testo")
    assert len(digest) == 64
    int(digest, 16)


def test_compare_core_fields_same_content_hash() -> None:
    a = {"content_hash": "abc123", "title": "X"}
    b = {"content_hash": "abc123", "title": "Y"}
    assert compare_core_fields(a, b) is True


def test_compare_core_fields_same_url_matches() -> None:
    a = {"source_url": "https://example.com/ad/1?utm_source=x", "title": None}
    b = {"source_url": "https://example.com/ad/1", "title": None}
    assert compare_core_fields(a, b) is True


def test_compare_core_fields_same_title_and_description_matches() -> None:
    a = {"title": "  Ciao   Mondo ", "description": "Testo   qui"}
    b = {"title": "ciao mondo", "description": "testo qui"}
    assert compare_core_fields(a, b) is True


def test_compare_core_fields_different_ads_do_not_match() -> None:
    a = {"title": "Annuncio A", "description": "Descrizione A", "source_url": "https://a.com/1"}
    b = {"title": "Annuncio B", "description": "Descrizione B", "source_url": "https://b.com/2"}
    assert compare_core_fields(a, b) is False


def test_compare_core_fields_empty_titles_do_not_falsely_match() -> None:
    """Due annunci entrambi senza titolo/URL non devono risultare 'uguali'
    solo perché entrambi i campi sono vuoti."""
    a = {"title": None, "description": None}
    b = {"title": None, "description": None}
    assert compare_core_fields(a, b) is False
