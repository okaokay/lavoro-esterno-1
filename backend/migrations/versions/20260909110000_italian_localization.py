"""Attiva il prompt italiano per i nuovi riepiloghi AI.

Revision ID: 20260909110000
Revises: 20260909103000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260909110000"
down_revision: str | None = "20260909103000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # I job e le versioni esistenti restano congelati su summary-v1. Cambia
    # soltanto la configurazione globale usata per creare i prossimi job.
    op.execute(
        sa.text(
            "UPDATE ai_settings "
            "SET prompt_version='summary-v2-it', revision=revision+1, updated_at=now() "
            "WHERE prompt_version='summary-v1'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE ai_settings "
            "SET prompt_version='summary-v1', revision=revision+1, updated_at=now() "
            "WHERE prompt_version='summary-v2-it'"
        )
    )
