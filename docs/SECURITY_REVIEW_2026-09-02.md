# Security review interna — 2 settembre 2026

## Scope e metodo

Review di autenticazione/MFA, RBAC/IDOR, export, URL firmati, SSRF media,
cancellazione GDPR, injection, logging sensibile, reverse proxy, container e
dipendenze. Questa attività non sostituisce un penetration test indipendente.

Verifiche eseguite localmente:

- `ruff check .`: superato;
- `pytest`: 121 superati, 5 test browser scraper opzionali saltati;
- Bandit 1.9.4, soglia Medium/High: nessun rilievo;
- `pip-audit` 2.10.1: nessuna vulnerabilità nota dopo remediation;
- `npm audit --audit-level=high`: zero vulnerabilità dopo remediation;
- Trivy config scan: nessun rilievo High/Critical dopo remediation;
- migrazioni Alembic applicate realmente a PostgreSQL 17 temporaneo fino a
  `20260902090000`.
- build Docker backend/frontend e validazione `docker compose config`:
  superate; utenti runtime verificati `app` e UID 101.

## Rilievi e remediation

| Severità | Rilievo | Esito |
|---|---|---|
| High | Vite vulnerabile a bypass `server.fs.deny` su Windows | Risolto aggiornando Vite 8.2.2/plugin React 6.1.1; audit finale pulito. |
| Medium | React Router/esbuild obsoleti | Risolto con React Router 7.18.3 e Vite 8.2.2. |
| Medium | `python-jose` installava `ecdsa` con advisory senza fix | Sostituito con PyJWT 2.13; audit finale pulito. |
| High | URL export firmato emesso dal listing senza evento download | Risolto: URL esclusivamente dall'endpoint download auditato. |
| High | Operator poteva vedere/scaricare export di altri utenti | Risolto: ownership server-side; Admin mantiene supervisione globale. |
| High | Tutti i ruoli ricevevano telefoni completi | Risolto con masking, grant individuale e audit dei display completi. |
| Medium | Header browser incompleti | Aggiunti Permissions-Policy e Cross-Origin-Opener-Policy; CSP/HSTS restano parte della configurazione TLS di produzione. |
| High | Container backend e frontend eseguiti come root | Risolto con utenti non privilegiati dedicati e frontend nginx-unprivileged sulla porta 8080; scan config finale pulito. |

## Automazione e residui

`.github/workflows/security.yml` blocca nuovi High/Critical tramite Bandit,
pip-audit, npm audit, dependency review e Trivy. Su schedule/manuale avvia
uno stack effimero e produce report OWASP ZAP baseline/OpenAPI.
I Medium devono essere corretti oppure accompagnati da un'accettazione del
rischio motivata e tracciata nella relativa issue/PR e nel report del run.

Residui obbligatori prima del go-live:

- archiviare gli scan completi Trivy immagini e ZAP prodotti dal runner CI;
- commissionare penetration test autenticato indipendente;
- configurare TLS/HSTS/CSP con i domini MinIO definitivi e un secret manager;
- provare backup e restore in ambiente staging;
- nessun rilievo High/Critical può essere accettato come rischio residuo.

Playwright non è stato rieseguito localmente in questa sessione perché la
suite richiede uno stack persistente con account Admin 2FA già iscritto; resta
un controllo obbligatorio del runner/staging prima del rilascio.
