"""users: aggiunge security_stamp_at

Revision ID: 20260828090000
Revises: 20260827120000
Create Date: 2026-08-28 09:00:00

Aggiunge `users.security_stamp_at`: timestamp di "validità minima" dei JWT
emessi per l'utente (claim `sst`, confrontato in app/security/deps.py).
Aggiornarlo invalida in blocco tutti i token precedentemente emessi (logout
con blacklist puntuale del jti a parte, gestita solo in Redis, non qui) —
usato da cambio password e reset/disattivazione 2FA. `server_default=now()`
evita di dover fare un backfill esplicito delle righe già esistenti.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260828090000"
down_revision: str | None = "20260827120000"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "security_stamp_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "security_stamp_at")
