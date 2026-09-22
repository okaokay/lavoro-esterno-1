"""sources: aggiunge scrape_config

Revision ID: 20260830090000
Revises: 20260829091500
Create Date: 2026-08-30 09:00:00

Aggiunge `sources.scrape_config` (JSONB, nullable): configurazione del
motore di scraping generico (`app/scrapers/generic.py`) per la fonte —
URL di partenza, selettori CSS per link annunci/paginazione/campi, tetti
di sicurezza (`max_pages`/`max_ads_per_run`). Nullable perché le fonti
già registrate come classi Python stub (`app/scrapers/registry.py`)
restano tali finché non vengono riconfigurate tramite l'app con questo
meccanismo (vedi PROGETTO.md § 4).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260830090000"
down_revision: str | None = "20260829091500"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("scrape_config", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sources", "scrape_config")
