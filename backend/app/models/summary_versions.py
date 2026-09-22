"""Modello `SummaryVersion`: versione di un riepilogo generato da AI per un
Record. Versionato perché il riepilogo può
essere rigenerato quando arrivano nuovi annunci/fonti."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin, utcnow


class SummaryVersion(UUIDPKMixin, Base):
    __tablename__ = "summary_versions"

    record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    record_content_revision: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    # Struttura attesa (vedi app/services/summary_generator.py e
    # app/schemas/records.py per lo schema Pydantic corrispondente):
    # {
    #   "summary": str,
    #   "advertisement_information": [...],
    #   "forum_information": [...],
    #   "unverified_claims": [...],
    #   "sources": [...],
    # }
    summary_json: Mapped[dict] = mapped_column(JSONB, nullable=False)

    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_provider: Mapped[str] = mapped_column(String(50), default="openai", nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), default="summary-v1", nullable=False)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    input_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    generation_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("summary_generation_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
