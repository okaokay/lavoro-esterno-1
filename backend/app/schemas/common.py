"""Base condivisa per gli schemi di risposta "view" consumati direttamente
dal frontend senza un layer di mapping esplicito.

Il frontend (vedi `frontend/src/api/*.ts`) usa due pattern distinti:

1. Alcuni moduli (es. `auth.ts`) leggono una risposta snake_case e la
   mappano esplicitamente in un DTO camelCase TypeScript (`mapUser(dto)`).
2. Altri moduli (es. `dashboard.ts`, `records.ts`, `sources.ts`,
   `exports.ts`, `admin.ts`) chiamano `apiRequest<T>(...)` passando
   DIRETTAMENTE il tipo camelCase come generic, senza alcuna funzione di
   mapping intermedia: per questi endpoint il backend deve quindi
   rispondere già in camelCase.

Gli schemi Pydantic per il secondo gruppo di endpoint ereditano da
`CamelModel`: usiamo `alias_generator=to_camel` (i campi restano scritti in
snake_case, idiomatico in Python) più `populate_by_name=True` (permette di
costruire le istanze passando comunque i nomi snake_case lato server) e
lasciamo che FastAPI serializzi "by alias" (comportamento di default per le
route), producendo così JSON camelCase.

Gli schemi per gli endpoint "storici" con mapping esplicito lato frontend
(es. `app/schemas/auth.py`, `app/schemas/records.py:RecordDetail`) NON
devono usare questa base, per non alterare un contratto già in uso.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
