"""initial schema

Revision ID: 20260827120000
Revises:
Create Date: 2026-08-27 12:00:00

Crea l'intero schema iniziale (tutte le tabelle e gli enum nativi Postgres).
Scritta manualmente (non da autogenerate) per garantire correttezza in un
ambiente in cui Alembic potrebbe non essere eseguibile durante lo sviluppo
di questo scaffold.

La FK circolare `records.canonical_ad_id -> advertisements.id` viene aggiunta
con un ALTER TABLE separato DOPO la creazione di `advertisements`, perché le
due tabelle si referenziano a vicenda e nessuna delle due può quindi
dichiarare la propria FK verso l'altra nella propria CREATE TABLE iniziale.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260827120000"
down_revision: str | None = None
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    # --- Enum nativi Postgres ------------------------------------------------
    # `create_type=False` su ogni istanza: il tipo viene creato UNA SOLA
    # VOLTA esplicitamente nel loop sotto (`enum_type.create(...)`). Senza
    # questo flag, SQLAlchemy tenta di ri-creare lo stesso tipo enum una
    # seconda volta come effetto collaterale di `op.create_table` (l'evento
    # DDL "before create" associato alla colonna enum spara comunque un
    # `CREATE TYPE`), il che con Postgres genera `DuplicateObjectError`
    # anche se l'enum esiste già (bug osservato e corretto durante il primo
    # avvio reale dello stack con `docker compose up`).
    user_role = postgresql.ENUM(
        "admin", "operator", "viewer", name="user_role", create_type=False
    )
    source_priority = postgresql.ENUM(
        "high", "medium", "low", name="source_priority", create_type=False
    )
    source_status = postgresql.ENUM(
        "healthy", "degraded", "offline", name="source_status", create_type=False
    )
    advertisement_status = postgresql.ENUM(
        "active", "removed", "invalid", name="advertisement_status", create_type=False
    )
    media_classification = postgresql.ENUM(
        "explicit", "safe", "unclassified", name="media_classification", create_type=False
    )
    scrape_run_status = postgresql.ENUM(
        "running", "completed", "failed", name="scrape_run_status", create_type=False
    )
    export_type = postgresql.ENUM(
        "text_only", "complete_media", "safe_complete", name="export_type", create_type=False
    )
    export_status = postgresql.ENUM(
        "pending", "processing", "ready", "failed", name="export_status", create_type=False
    )

    bind = op.get_bind()
    for enum_type in (
        user_role,
        source_priority,
        source_status,
        advertisement_status,
        media_classification,
        scrape_run_status,
        export_type,
        export_status,
    ):
        enum_type.create(bind, checkfirst=True)

    # --- users -----------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", user_role, nullable=False, server_default="viewer"),
        sa.Column("totp_secret_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("backup_codes_hash", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # --- sources -----------------------------------------------------------
    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("priority", source_priority, nullable=False, server_default="medium"),
        sa.Column("status", source_status, nullable=False, server_default="healthy"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_sources"),
        sa.UniqueConstraint("slug", name="uq_sources_slug"),
    )
    op.create_index("ix_sources_slug", "sources", ["slug"])

    # --- records (senza ancora la FK verso advertisements) ------------------
    op.create_table(
        "records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("phone_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("phone_lookup_hash", sa.String(length=64), nullable=False),
        sa.Column("canonical_ad_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_records"),
        sa.UniqueConstraint("phone_lookup_hash", name="uq_records_phone_lookup_hash"),
    )
    op.create_index("ix_records_phone_lookup_hash", "records", ["phone_lookup_hash"])

    # --- advertisements ------------------------------------------------------
    op.create_table(
        "advertisements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("status", advertisement_status, nullable=False, server_default="active"),
        sa.PrimaryKeyConstraint("id", name="pk_advertisements"),
        sa.ForeignKeyConstraint(
            ["record_id"], ["records.id"], name="fk_advertisements_record_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name="fk_advertisements_source_id", ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_advertisements_record_id", "advertisements", ["record_id"])
    op.create_index("ix_advertisements_source_id", "advertisements", ["source_id"])
    op.create_index("ix_advertisements_content_hash", "advertisements", ["content_hash"])

    # --- chiusura del ciclo record <-> advertisement -------------------------
    op.create_foreign_key(
        "fk_records_canonical_ad_id",
        "records",
        "advertisements",
        ["canonical_ad_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- media -----------------------------------------------------------
    op.create_table(
        "media",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("advertisement_id", sa.Uuid(), nullable=False),
        sa.Column("original_object_key", sa.Text(), nullable=False),
        sa.Column("derived_object_key", sa.Text(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("perceptual_hash", sa.String(length=64), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column(
            "classification", media_classification, nullable=False, server_default="unclassified"
        ),
        sa.Column("classification_confidence", sa.Float(), nullable=True),
        sa.Column("classifier_version", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_media"),
        sa.ForeignKeyConstraint(
            ["advertisement_id"],
            ["advertisements.id"],
            name="fk_media_advertisement_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_media_advertisement_id", "media", ["advertisement_id"])
    op.create_index("ix_media_sha256", "media", ["sha256"])

    # --- canonical_history -----------------------------------------------
    op.create_table(
        "canonical_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("previous_advertisement_id", sa.Uuid(), nullable=True),
        sa.Column("new_advertisement_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("overridden_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_canonical_history"),
        sa.ForeignKeyConstraint(
            ["record_id"], ["records.id"], name="fk_canonical_history_record_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["previous_advertisement_id"],
            ["advertisements.id"],
            name="fk_canonical_history_previous_advertisement_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["new_advertisement_id"],
            ["advertisements.id"],
            name="fk_canonical_history_new_advertisement_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["overridden_by_user_id"],
            ["users.id"],
            name="fk_canonical_history_overridden_by_user_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_canonical_history_record_id", "canonical_history", ["record_id"])

    # --- scrape_runs -----------------------------------------------------
    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", scrape_run_status, nullable=False, server_default="running"),
        sa.Column("items_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id", name="pk_scrape_runs"),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name="fk_scrape_runs_source_id", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_scrape_runs_source_id", "scrape_runs", ["source_id"])

    # --- scrape_errors -----------------------------------------------------
    op.create_table(
        "scrape_errors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scrape_run_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_scrape_errors"),
        sa.ForeignKeyConstraint(
            ["scrape_run_id"],
            ["scrape_runs.id"],
            name="fk_scrape_errors_scrape_run_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_scrape_errors_scrape_run_id", "scrape_errors", ["scrape_run_id"])

    # --- media_classification_history ---------------------------------------
    op.create_table(
        "media_classification_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("previous_classification", media_classification, nullable=True),
        sa.Column("new_classification", media_classification, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("manual_override", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_media_classification_history"),
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["media.id"],
            name="fk_media_classification_history_media_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["users.id"],
            name="fk_media_classification_history_changed_by_user_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_media_classification_history_media_id", "media_classification_history", ["media_id"]
    )

    # --- summary_versions -----------------------------------------------
    op.create_table(
        "summary_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("summary_json", postgresql.JSONB(), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_summary_versions"),
        sa.ForeignKeyConstraint(
            ["record_id"], ["records.id"], name="fk_summary_versions_record_id", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_summary_versions_record_id", "summary_versions", ["record_id"])

    # --- export_jobs -----------------------------------------------------
    op.create_table(
        "export_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=True),
        sa.Column("type", export_type, nullable=False),
        sa.Column("status", export_status, nullable=False, server_default="pending"),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manifest_json", postgresql.JSONB(), nullable=True),
        sa.Column("object_key", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_export_jobs"),
        sa.ForeignKeyConstraint(
            ["record_id"], ["records.id"], name="fk_export_jobs_record_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            name="fk_export_jobs_requested_by_user_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_export_jobs_record_id", "export_jobs", ["record_id"])

    # --- audit_log -----------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=200), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=True),
        sa.Column("details_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_audit_log_user_id", ondelete="SET NULL"
        ),
    )
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("export_jobs")
    op.drop_table("summary_versions")
    op.drop_table("media_classification_history")
    op.drop_table("scrape_errors")
    op.drop_table("scrape_runs")
    op.drop_table("canonical_history")
    op.drop_table("media")
    op.drop_constraint("fk_records_canonical_ad_id", "records", type_="foreignkey")
    op.drop_table("advertisements")
    op.drop_table("records")
    op.drop_table("sources")
    op.drop_table("users")

    bind = op.get_bind()
    for enum_name in (
        "export_status",
        "export_type",
        "scrape_run_status",
        "media_classification",
        "advertisement_status",
        "source_status",
        "source_priority",
        "user_role",
    ):
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)
