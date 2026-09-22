"""Modello `ExportJob`: richiesta asincrona di esportazione (testo, media
completi, o solo media "safe"), eseguita da un worker Celery dedicato."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin, utcnow

ExportType = sa.Enum(
    "text_only", "complete_media", "safe_complete", name="export_type", create_type=True
)
ExportStatus = sa.Enum(
    "pending", "processing", "ready", "failed", name="export_status", create_type=True
)


class ExportJob(UUIDPKMixin, Base):
    __tablename__ = "export_jobs"
    __table_args__ = (
        # Liste/filtri per stato+data (GET /exports) e pulizia per retention.
        Index("ix_export_jobs_status_requested_at", "status", "requested_at"),
    )

    # Nullable: un export può riguardare un singolo record oppure essere bulk
    # (es. tutti i record che soddisfano un certo filtro), nel qual caso il
    # dettaglio è nel manifest_json piuttosto che in una FK singola.
    record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("records.id", ondelete="CASCADE"), nullable=True, index=True
    )

    type: Mapped[str] = mapped_column(ExportType, nullable=False)
    status: Mapped[str] = mapped_column(ExportStatus, default="pending", nullable=False)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Calcolata alla creazione come requested_at + EXPORT_RETENTION_DAYS (vedi
    # app/api/v1/exports.py:create_export). Usata dal task periodico
    # app.workers.tasks_maintenance.cleanup_expired_data per rimuovere
    # l'oggetto MinIO e il job scaduti; l'evento resta nell'audit separato.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    manifest_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    record_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_uncompressed_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    archive_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    include_clear_phone: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ExportJobRecord(Base):
    __tablename__ = "export_job_records"

    export_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("export_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("records.id", ondelete="CASCADE"), primary_key=True, index=True
    )
