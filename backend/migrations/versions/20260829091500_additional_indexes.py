"""indici aggiuntivi: query composite, full-text, retention

Revision ID: 20260829091500
Revises: 20260829090000
Create Date: 2026-08-29 09:15:00

Indici mancanti individuati rileggendo i pattern di query reali del backend
(`app/api/v1/*.py`, `app/workers/tasks_*.py`) dopo aver completato le
migrazioni iniziali:

- `advertisements(source_id, status)`: filtro "annunci attivi di una
  fonte", usato dalla selezione canonica (`app/services/canonical.py`) e
  da eventuali viste di dashboard.
- Full-text GIN su `advertisements` (title+description): indice
  funzionale (nessuna nuova colonna, niente colonna tsvector generata) —
  sufficiente per il volume atteso in questa fase; se il volume di ricerche
  full-text crescesse, valutare una colonna `tsvector` generata/materializzata
  con trigger, più performante ma più costosa da mantenere.
- `media(perceptual_hash)`: oggi assente, necessario per il matching pHash
  (TODO già presente in `app/services/dedup.py`).
- `export_jobs(status, requested_at)`: liste/filtri per stato+data.
- `export_jobs(requested_by_user_id)`: FK oggi priva di indice.
- `scrape_errors(created_at)` e `audit_log(created_at)`: necessari per le
  query di retention di `app.workers.tasks_maintenance.cleanup_expired_data`
  (senza questi indici, ogni run notturno farebbe un full table scan).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260829091500"
down_revision: str | None = "20260829090000"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

_FULLTEXT_INDEX_NAME = "ix_advertisements_fulltext"


def upgrade() -> None:
    op.create_index(
        "ix_advertisements_source_id_status",
        "advertisements",
        ["source_id", "status"],
    )
    # Indice funzionale GIN per la ricerca full-text su titolo+descrizione.
    # Non esprimibile con `op.create_index` in modo portabile (richiede
    # un'espressione, non solo nomi di colonna): SQL diretto.
    op.execute(
        f"""
        CREATE INDEX {_FULLTEXT_INDEX_NAME}
        ON advertisements
        USING GIN (to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(description, '')))
        """
    )
    op.create_index("ix_media_perceptual_hash", "media", ["perceptual_hash"])
    op.create_index(
        "ix_export_jobs_status_requested_at",
        "export_jobs",
        ["status", "requested_at"],
    )
    op.create_index(
        "ix_export_jobs_requested_by_user_id", "export_jobs", ["requested_by_user_id"]
    )
    op.create_index("ix_scrape_errors_created_at", "scrape_errors", ["created_at"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_index("ix_scrape_errors_created_at", table_name="scrape_errors")
    op.drop_index("ix_export_jobs_requested_by_user_id", table_name="export_jobs")
    op.drop_index("ix_export_jobs_status_requested_at", table_name="export_jobs")
    op.drop_index("ix_media_perceptual_hash", table_name="media")
    op.execute(f"DROP INDEX IF EXISTS {_FULLTEXT_INDEX_NAME}")
    op.drop_index("ix_advertisements_source_id_status", table_name="advertisements")
