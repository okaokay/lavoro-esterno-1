"""Bootstrap del primo utente Admin.

Nessun endpoint API può creare il primissimo utente: `POST /admin/users`
richiede già un Admin autenticato CON 2FA attiva (vedi `app/api/v1/
admin.py`), per impedire che un account admin compromesso senza 2FA possa
da solo alterare la base utenti. Questo è corretto come modello di
sicurezza, ma crea un problema del "chi crea il primo admin?": la risposta
è questo script, eseguito una tantum direttamente contro il database,
FUORI dal perimetro HTTP/RBAC.

Uso (dentro il container `api`, con lo stack già avviato):

    docker compose exec api python -m app.scripts.create_admin \\
        --email admin@lavoro.internal --password "una-password-forte"

L'utente creato ha `totp_enabled=False`: la 2FA è obbligatoria dal login
per il ruolo admin, quindi al primo login riceverà `status=
"mfa_setup_required"` e dovrà attivarla con `POST /auth/setup-2fa` +
`POST /auth/verify-2fa` (vedi `app/security/deps.py:get_current_user`)
prima di poter usare qualunque altro endpoint, incluse le operazioni admin
più sensibili (protette anche da `require_admin_with_2fa`).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.users import User
from app.security.password import WeakPasswordError, hash_password, validate_password_strength


async def create_admin(email: str, password: str) -> None:
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing is not None:
            print(f"Utente '{email}' già esistente (id={existing.id}, role={existing.role}).")
            sys.exit(1)

        try:
            validate_password_strength(password, email=email)
        except WeakPasswordError as exc:
            print(f"Password non valida: {exc}")
            sys.exit(1)

        user = User(
            email=email,
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"Utente admin creato: id={user.id} email={user.email}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Crea il primo utente Admin del sistema.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    asyncio.run(create_admin(args.email, args.password))


if __name__ == "__main__":
    main()
