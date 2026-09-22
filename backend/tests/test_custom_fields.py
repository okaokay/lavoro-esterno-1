"""Persistenza, aggregazione ed export dei campi dinamici delle fonti."""

import csv
import io
import json
import uuid
from types import SimpleNamespace

from app.api.v1.records import (
    _aggregate_custom_fields,
    _tags_from_custom_fields,
    _tags_from_groups,
)
from app.schemas.records import CustomFieldValueRead
from app.scrapers.generic import GenericScraper
from app.services.scrape_ingest import (
    _changed_fields,
    advertisement_content_hash,
    media_set_hash,
    non_empty_custom_field_count,
    occurrence_fingerprint,
)
from app.workers.tasks_exports import _csv_bytes


def _scraper(fields: dict) -> GenericScraper:
    return GenericScraper(
        slug="custom-test",
        base_url="https://example.test",
        config={"start_urls": [], "fields": fields, "rate_limit_seconds": 0},
    )


def test_normalize_preserves_every_configured_non_core_field() -> None:
    scraper = _scraper(
        {
            "title": {},
            "phone": {},
            "images": {},
            "tags": {},
            "city": {},
            "empty": {},
        }
    )
    normalized = scraper.normalize(
        {
            "title": "Listing",
            "phone": "+390000000000",
            "images": ["/image.jpg"],
            "tags": ["one", "two"],
            "city": "Roma\nCentro",
            "empty": None,
            "source_url": "https://example.test/ad/1",
        }
    )

    assert normalized["custom_fields"] == {
        "tags": ["one", "two"],
        "city": "Roma\nCentro",
        "empty": None,
    }
    core = {"title", "phone", "images", "source_url"}
    assert not core & normalized["custom_fields"].keys()


def test_record_schema_accepts_structured_custom_fields() -> None:
    value = CustomFieldValueRead(
        value=[{"poster": "/poster.jpg", "video": "/video.mp4"}],
        source_id=uuid.uuid4(),
        source_name="Source",
        source_code="source",
        advertisement_id=uuid.uuid4(),
        is_canonical=True,
    )

    assert value.value == [{"poster": "/poster.jpg", "video": "/video.mp4"}]


def test_custom_fields_change_content_hash_independently_of_key_order() -> None:
    first = {
        "title": "A",
        "description": "B",
        "custom_fields": {"city": "Roma", "age": "30"},
    }
    reordered = {
        "title": "A",
        "description": "B",
        "custom_fields": {"age": "30", "city": "Roma"},
    }
    changed = {
        "title": "A",
        "description": "B",
        "custom_fields": {"city": "Milano", "age": "30"},
    }

    assert advertisement_content_hash(first) == advertisement_content_hash(reordered)
    assert advertisement_content_hash(first) != advertisement_content_hash(changed)


def test_non_empty_custom_fields_contribute_to_completeness() -> None:
    fields = {"city": "Roma", "tags": ["one"], "blank": "  ", "empty": [], "missing": None}
    assert non_empty_custom_field_count(fields) == 2


def test_tags_accept_scalar_or_list_and_are_trimmed_and_deduplicated() -> None:
    assert _tags_from_custom_fields({"tags": "  single  "}) == ["single"]
    assert _tags_from_custom_fields({"tags": ["one", " one ", "", "two", None]}) == [
        "one",
        "two",
    ]


def test_record_groups_arbitrary_fields_from_every_source_with_provenance() -> None:
    canonical_id = uuid.uuid4()
    source_one = uuid.uuid4()
    source_two = uuid.uuid4()
    rows = [
        (
            SimpleNamespace(
                id=canonical_id,
                custom_fields={"paperino": "qua", "Shared": "canonical", "tags": ["one"]},
            ),
            source_one,
            "Source one",
            "source_one",
        ),
        (
            SimpleNamespace(
                id=uuid.uuid4(),
                custom_fields={"pippo": "pluto", "Shared": "other", "tags": ["two", "one"]},
            ),
            source_two,
            "Source two",
            "source_two",
        ),
    ]

    groups = _aggregate_custom_fields(rows, canonical_id)
    by_name = {group.name: group for group in groups}

    assert set(by_name) == {"paperino", "pippo", "Shared", "tags"}
    assert by_name["paperino"].values[0].source_name == "Source one"
    assert by_name["paperino"].values[0].is_canonical is True
    assert [entry.value for entry in by_name["Shared"].values] == ["canonical", "other"]
    assert _tags_from_groups(groups) == ["one", "two"]


def test_record_groups_keep_structured_values() -> None:
    advertisement_id = uuid.uuid4()
    rows = [
        (
            SimpleNamespace(
                id=advertisement_id,
                custom_fields={"details": {"eta": "26", "tipo_annuncio": "privato"}},
            ),
            uuid.uuid4(),
            "Source",
            "source",
        )
    ]

    groups = _aggregate_custom_fields(rows, advertisement_id)

    assert groups[0].values[0].value == {"eta": "26", "tipo_annuncio": "privato"}


def test_record_groups_keep_case_distinct_and_drop_only_same_source_duplicates() -> None:
    source_id = uuid.uuid4()
    other_source_id = uuid.uuid4()
    rows = [
        (
            SimpleNamespace(
                id=uuid.uuid4(),
                custom_fields={"Field": "same", "field": "different", "empty": "  "},
            ),
            source_id,
            "Source",
            "source",
        ),
        (
            SimpleNamespace(id=uuid.uuid4(), custom_fields={"Field": "same"}),
            source_id,
            "Source",
            "source",
        ),
        (
            SimpleNamespace(id=uuid.uuid4(), custom_fields={"Field": "same"}),
            other_source_id,
            "Other source",
            "other",
        ),
    ]

    groups = _aggregate_custom_fields(rows, None)
    by_name = {group.name: group for group in groups}

    assert set(by_name) == {"Field", "field"}
    assert len(by_name["Field"].values) == 2
    assert by_name["field"].values[0].value == "different"


def test_export_csv_serializes_custom_fields_as_deterministic_json() -> None:
    payload = _csv_bytes(
        [
            {
                "id": "ad-1",
                "custom_fields": {
                    "tags": ["one"],
                    "city": "Roma",
                    "details": {"tipo_annuncio": "privato", "eta": "26"},
                },
            }
        ],
        ["id", "custom_fields"],
    )
    row = next(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))

    assert row["custom_fields"] == (
        '{"city":"Roma","details":{"eta":"26","tipo_annuncio":"privato"},'
        '"tags":["one"]}'
    )
    assert json.loads(row["custom_fields"])["details"] == {
        "eta": "26",
        "tipo_annuncio": "privato",
    }


def test_media_set_hash_is_order_independent_and_deduplicated() -> None:
    assert media_set_hash(["b", "a", "a"]) == media_set_hash(["a", "b"])
    assert media_set_hash(["a"]) != media_set_hash(["b"])


def test_occurrence_fingerprint_combines_content_and_media() -> None:
    assert occurrence_fingerprint("content", "media") == occurrence_fingerprint("content", "media")
    assert occurrence_fingerprint("content", "media") != occurrence_fingerprint(
        "content-2", "media"
    )


def test_changed_fields_reports_only_material_differences() -> None:
    advertisement = SimpleNamespace(
        title="Title",
        description="First\nSecond",
        custom_fields={"paperino": ["uno", "due"]},
    )
    unchanged = {
        "title": "Title",
        "description": "First\nSecond",
        "custom_fields": {"paperino": ["uno", "due"]},
    }
    assert _changed_fields(advertisement, unchanged, False) == []
    changed = {**unchanged, "custom_fields": {"paperino": ["uno", "tre"]}}
    assert _changed_fields(advertisement, changed, True) == ["customFields", "media"]
