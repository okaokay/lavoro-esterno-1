"""Messaggi italiani riutilizzabili esposti dalle API."""

from __future__ import annotations

MESSAGES = {
    "validation.required": "Campo obbligatorio.",
    "validation.string": "Il valore deve essere una stringa.",
    "validation.integer": "Il valore deve essere un numero intero.",
    "validation.number": "Il valore deve essere un numero.",
    "validation.boolean": "Il valore deve essere vero o falso.",
    "validation.uuid": "Il valore deve essere un UUID valido.",
    "validation.datetime": "Il valore deve essere una data e ora valide.",
    "validation.list": "Il valore deve essere un elenco.",
    "validation.extra": "Campo non consentito.",
    "validation.invalid": "Valore non valido.",
}


def message(key: str) -> str:
    return MESSAGES.get(key, MESSAGES["validation.invalid"])


def validation_message(error_type: str) -> str:
    if error_type == "missing":
        return message("validation.required")
    if "string" in error_type:
        return message("validation.string")
    if "int" in error_type:
        return message("validation.integer")
    if "float" in error_type or "decimal" in error_type:
        return message("validation.number")
    if "bool" in error_type:
        return message("validation.boolean")
    if "uuid" in error_type:
        return message("validation.uuid")
    if "datetime" in error_type or error_type.startswith("date_"):
        return message("validation.datetime")
    if "list" in error_type:
        return message("validation.list")
    if error_type == "extra_forbidden":
        return message("validation.extra")
    return message("validation.invalid")
