#!/bin/sh
# =============================================================================
# Backup MinIO - Lavoro Esterno
# -----------------------------------------------------------------------------
# Eseguito dal servizio "backup-minio" (immagine ufficiale minio/mc, client
# MinIO, nessuna immagine custom necessaria).
#
# Strategia: REPLICA continua (non snapshot datati), tramite `mc mirror
# --overwrite --remove`: il contenuto del bucket viene rispecchiato sul
# volume locale "minio-backups" a ogni ciclo, inclusa la rimozione dei file
# non più presenti nel bucket sorgente. È una delle due strategie indicate
# nel checklist di progetto ("MinIO: versioning o replica") — qui si è
# scelta la replica per semplicità: nessuna gestione di versioni storiche,
# un solo stato "specchio" sempre aggiornato.
#
# Conseguenza pratica: BACKUP_RETENTION_DAYS NON si applica a questo script
# (non ci sono snapshot datati da ruotare, a differenza di
# backup-postgres.sh) — la variabile resta letta/passata per coerenza con
# l'altro servizio di backup e per una eventuale futura evoluzione verso
# snapshot periodici invece della replica continua.
#
# Come per Postgres: backup LOCALE (stesso host Docker), non off-site.
# Questo file deve essere mantenuto con terminatori LF (vedi .gitattributes).
# Quando si sceglie l'hosting definitivo, sostituire il target locale con un
# secondo endpoint S3-compatible remoto (`mc mirror` supporta alias remoti
# nello stesso identico modo) — vedi docs/DATABASE.md § Backup.
# =============================================================================
set -eu

BACKUP_DIR="/backups/media"
SCHEME="http"
if [ "${MINIO_SECURE:-false}" = "true" ]; then
    SCHEME="https"
fi

mkdir -p "${BACKUP_DIR}"

mc alias set source "${SCHEME}://${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}" >/dev/null

run_mirror() {
    echo "[backup-minio] Mirroring bucket '${MINIO_BUCKET}' -> ${BACKUP_DIR}"
    if mc mirror --overwrite --remove "source/${MINIO_BUCKET}" "${BACKUP_DIR}"; then
        return 0
    fi
    echo "[backup-minio] Mirror non riuscito (bucket assente o non raggiungibile?)." >&2
    return 1
}

if [ "${1:-}" = "--once" ]; then
    run_mirror
    exit 0
fi

while true; do
    if run_mirror; then
        sleep 86400
    else
        echo "[backup-minio] Riprovo tra 60 secondi." >&2
        sleep 60
    fi
done
