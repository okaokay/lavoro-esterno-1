"""Funzioni pure di supporto alla ricerca record (`GET /records/search`).

Isolano decisioni di dominio non banali dal router, per poterle testare
senza database:

- `looks_like_full_phone`: euristica per decidere se il valore digitato nel
  filtro "phone" è probabilmente un numero completo (nel qual caso ha senso
  cercarlo per hash esatto) oppure solo un frammento/prefisso (nel qual
  caso l'hash esatto non troverebbe nulla, vedi commento sotto).
- `confidence_to_status`: mappa la confidence (0..1) dell'annuncio canonico
  sullo status "verified"/"unverified" atteso dal frontend.
"""

from __future__ import annotations

from app.services.phone_crypto import PhoneCryptoError, normalize_phone

# Soglia di confidence sopra la quale consideriamo un record "verified".
# Il dominio non ha (ancora) un vero workflow di verifica umana: usiamo la
# confidence di matching dell'annuncio canonico come proxy pragmatico.
# Non esiste attualmente alcun segnale per lo status "flagged" (richiederebbe
# un meccanismo di segnalazione manuale, non ancora implementato): vedi
# l'uso di questa soglia in app/api/v1/records.py per il dettaglio.
VERIFIED_CONFIDENCE_THRESHOLD = 0.85

# Lunghezza minima (in cifre) perché un valore digitato sia considerato un
# numero "probabilmente completo" piuttosto che un frammento/prefisso: i
# numeri italiani hanno tipicamente 9-10 cifre dopo il prefisso paese.
_MIN_FULL_PHONE_DIGITS = 9


def looks_like_full_phone(value: str) -> bool:
    """True se `value` normalizza a un numero di telefono valido E "completo".

    Perché serve: il telefono è salvato solo come `phone_lookup_hash` (HMAC
    del numero normalizzato — vedi `app/services/phone_crypto.py`). L'HMAC è
    deterministico ma cambia completamente anche per un solo carattere di
    differenza, quindi NON esiste modo di fare una ricerca "a prefisso"
    (`LIKE 'prefix%'`) su un hash. Se l'utente ha digitato un numero
    apparentemente completo possiamo calcolarne l'hash e fare un match
    esatto; se ha digitato solo un frammento (es. "333" o "1234"), l'unica
    strada corretta richiederebbe di decifrare `phone_encrypted` per OGNI
    record e confrontare in chiaro — costoso e, soprattutto, in contrasto col
    principio di minimizzazione che ha motivato la scelta di non tenere il
    numero in chiaro come colonna indicizzata.

    TODO: se in futuro serve una ricerca a prefisso efficiente, valutare un
    indice dedicato (es. hash troncato su prefissi di lunghezza fissa)
    invece di decifrare l'intero dataset ad ogni ricerca. Per ora, un filtro
    "phone" che non sembra un numero completo viene semplicemente ignorato
    dal router (la ricerca prosegue sugli altri criteri).
    """
    try:
        normalize_phone(value)
    except PhoneCryptoError:
        return False
    digits = "".join(ch for ch in value if ch.isdigit())
    return len(digits) >= _MIN_FULL_PHONE_DIGITS


def confidence_to_status(confidence: float | None) -> str:
    """Mappa la confidence dell'annuncio canonico sullo status del record."""
    if confidence is None:
        return "unverified"
    return "verified" if confidence >= VERIFIED_CONFIDENCE_THRESHOLD else "unverified"
