#!/bin/sh
# =============================================================================
# Ripristino manuale di un dump Postgres - Lavoro Esterno
# -----------------------------------------------------------------------------
# Procedura di ripristino "test di ripristino" richiesta dal checklist di
# progetto: NON automatizzata/schedulata (un ripristino è un'operazione
# distruttiva, va sempre eseguita consapevolmente da un umano), ma resa
# eseguibile con un singolo comando invece che con passi manuali psql/gzip.
#
# Uso (dal host, con lo stack già avviato):
#   docker compose exec backup-postgres sh /scripts/restore-postgres.sh \
#       /backups/lavoro_esterno_20260829_030000.sql.gz
#
# Per elencare i dump disponibili nel container:
#   docker compose exec backup-postgres ls -la /backups
#
# ATTENZIONE: questo script SOVRASCRIVE il contenuto del database indicato
# da POSTGRES_DB/POSTGRES_USER (lo stesso database applicativo, se eseguito
# Questo file deve essere mantenuto con terminatori LF (vedi .gitattributes).
# nell'ambiente di sviluppo/staging di default) con quanto contenuto nel
# dump. Non eseguire contro un database di produzione senza aver prima
# verificato di puntare all'istanza corretta.
# =============================================================================
set -eu

DUMP_FILE="${1:-}"
if [ -z "${DUMP_FILE}" ]; then
    echo "Uso: $0 <percorso-dump.sql.gz>" >&2
    echo "Dump disponibili in /backups:" >&2
    ls -la /backups 2>/dev/null >&2 || true
    exit 1
fi

if [ ! -f "${DUMP_FILE}" ]; then
    echo "File non trovato: ${DUMP_FILE}" >&2
    exit 1
fi

export PGPASSWORD="${POSTGRES_PASSWORD}"

echo "Sto per ripristinare '${DUMP_FILE}' su database '${POSTGRES_DB}' (host: postgres)."
echo "Questa operazione SOVRASCRIVE i dati esistenti. Premi Ctrl+C ora per annullare."
sleep 5

gunzip -c "${DUMP_FILE}" | psql -h postgres -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"

echo "Ripristino completato."
