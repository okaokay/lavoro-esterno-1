#!/bin/sh
# =============================================================================
# Backup Postgres - Lavoro Esterno
# -----------------------------------------------------------------------------
# Eseguito dal servizio "backup-postgres" (immagine postgres:17-alpine, che
# include già pg_dump/gzip/find, nessuna immagine custom necessaria).
#
# Strategia: dump logico completo (`pg_dump` in formato SQL semplice,
# compresso con gzip) una volta al giorno, salvato sul volume "postgres-
# backups" (distinto dal volume dati "postgres-data"), con rotazione dei
# dump più vecchi di BACKUP_RETENTION_DAYS giorni.
#
# Limite noto: il loop usa "sleep 86400", quindi il ritmo è "ogni 24h dal
# riavvio del container", non un orario fisso (niente vero cron in
# un'immagine minimale). Per un ambiente di produzione con requisiti di
# puntualità, sostituire con cron/host scheduler esterno che invochi questo
# stesso script una tantum (`sh /scripts/backup-postgres.sh --once`).
#
# Questo backup è LOCALE (stesso host Docker della sorgente): non è un
# backup off-site/disaster-recovery. Quando si sceglie l'hosting definitivo,
# Questo file deve essere mantenuto con terminatori LF (vedi .gitattributes).
# aggiungere qui uno step che copia i dump anche su uno storage remoto
# (S3-compatible, incluso lo stesso MinIO se esterno all'host, o un bucket
# cloud) — vedi docs/DATABASE.md § Backup.
# =============================================================================
set -eu

BACKUP_DIR="/backups"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
export PGPASSWORD="${POSTGRES_PASSWORD}"

run_backup() {
    timestamp="$(date +%Y%m%d_%H%M%S)"
    dest="${BACKUP_DIR}/lavoro_esterno_${timestamp}.sql.gz"
    sql_tmp="${BACKUP_DIR}/.lavoro_esterno_${timestamp}.sql.tmp"
    echo "[backup-postgres] Avvio dump verso ${dest}"

    # --clean --if-exists: il dump include i DROP necessari prima di ogni
    # CREATE, così il ripristino (restore-postgres.sh) funziona anche
    # contro un database che ha già le tabelle (il caso comune: sostituire
    # lo stato corrente con quello del backup), non solo contro uno vuoto.
    # POSIX sh non offre `pipefail`: scrivere prima il dump non compresso
    # evita che il successo di gzip nasconda un errore di pg_dump.
    if pg_dump -h postgres -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        --clean --if-exists > "${sql_tmp}" \
        && gzip -c "${sql_tmp}" > "${dest}.tmp"; then
        mv "${dest}.tmp" "${dest}"
        rm -f "${sql_tmp}"
        echo "[backup-postgres] Dump completato: ${dest} ($(du -h "${dest}" | cut -f1))"
    else
        echo "[backup-postgres] ERRORE durante il dump, file temporaneo rimosso" >&2
        rm -f "${sql_tmp}" "${dest}.tmp"
        return 1
    fi

    echo "[backup-postgres] Rotazione: rimuovo dump più vecchi di ${RETENTION_DAYS} giorni"
    find "${BACKUP_DIR}" -name 'lavoro_esterno_*.sql.gz' -mtime "+${RETENTION_DAYS}" -delete
}

mkdir -p "${BACKUP_DIR}"

if [ "${1:-}" = "--once" ]; then
    run_backup
    exit 0
fi

while true; do
    if run_backup; then
        sleep 86400
    else
        echo "[backup-postgres] Run fallito, riprovo tra 60 secondi." >&2
        sleep 60
    fi
done
