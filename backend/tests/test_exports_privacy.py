"""Vincoli di export, minimizzazione dati e cancellazione GDPR."""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.admin import AdminUserUpdate
from app.schemas.exports import ExportFilters, ExportJobCreate
from app.schemas.privacy import ErasureRequestCreate
from app.services.phone_crypto import mask_phone


def test_export_requires_exactly_one_explicit_scope() -> None:
    with pytest.raises(ValidationError):
        ExportJobCreate(type="text_only")
    with pytest.raises(ValidationError):
        ExportJobCreate(
            type="text_only",
            record_ids=[uuid.uuid4()],
            filters=ExportFilters(source="source-a"),
        )


def test_export_rejects_duplicate_record_ids() -> None:
    record_id = uuid.uuid4()
    with pytest.raises(ValidationError):
        ExportJobCreate(type="complete_media", record_ids=[record_id, record_id])


def test_export_filters_must_be_non_empty() -> None:
    with pytest.raises(ValidationError):
        ExportFilters()
    assert ExportFilters(source="source-a").source == "source-a"


def test_phone_mask_does_not_reveal_middle_digits() -> None:
    assert mask_phone("+393331234567") == "+39********67"
    assert "33312345" not in mask_phone("+393331234567")


def test_admin_update_accepts_phone_permission_without_role_change() -> None:
    update = AdminUserUpdate(can_view_clear_phone=True)
    assert update.role is None
    assert update.can_view_clear_phone is True


def test_erasure_contract_requires_reason_and_authorization_reference() -> None:
    with pytest.raises(ValidationError):
        ErasureRequestCreate(phone="+393331234567", reason="ok", authorization_reference="")
    request = ErasureRequestCreate(
        phone="+393331234567",
        reason="Richiesta verificata",
        authorization_reference="TICKET-123",
    )
    dumped = request.model_dump(by_alias=True)
    assert dumped["authorizationReference"] == "TICKET-123"
    assert "+393331234567" not in repr({"audit": request.authorization_reference})
