"""export_jobs: aggiunge expires_at

Revision ID: 20260829090000
Revises: 20260828090000
Create Date: 2026-08-29 09:00:00

Aggiunge `export_jobs.expires_at`, calcolata a runtime dall'API
(`app/api/v1/exports.py:create_export`/`retry_export`) come
`requested_at + EXPORT_RETENTION_DAYS`. Usata dal task periodico
`app.workers.tasks_maintenance.cleanup_expired_data` per individuare i
pacchetti di export da rimuovere da MinIO. Nullable perché le righe già
esistenti (create prima di questa migrazione) non hanno una scadenza nota:
restano semplicemente escluse dalla pulizia automatica finché non vengono
ricreate/ritentate.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260829090000"
down_revision: str | None = "20260828090000"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.add_column(
        "export_jobs",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("export_jobs", "expires_at")
