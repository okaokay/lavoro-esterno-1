# Riassunto sessione - Progetto "Lavoro Esterno"

## Aggiornamento Dashboard - 4 settembre 2026

Il controllo temporale della Dashboard non è più statico. Offre le finestre
24 ore, 7 giorni, 30 giorni e un intervallo personalizzato con data e ora nel
fuso `Europe/Rome`, limitato a 90 giorni. La scelta è conservata nella query
string (`range`, e per la modalità personalizzata `start`/`end` in UTC), quindi
sopravvive al reload e può essere condivisa tramite link.

Gli endpoint `GET /api/v1/dashboard/kpis`, `scraping-activity` e `activity`
accettano ora `start` ed `end`. Il backend rifiuta timestamp senza offset,
intervalli invertiti, date future e durate superiori a 90 giorni; senza
parametri usa le ultime 24 ore. Record creati ed errori sono confrontati con
la finestra precedente della stessa durata. Gli snapshot Total Records,
Active Sources, Active Exports e Source Health restano valori correnti.

“Refresh Data” attende tutte le richieste, mostra uno spinner, impedisce doppi
clic e riporta l'orario dell'ultimo aggiornamento completamente riuscito. Un
errore parziale mantiene i dati precedenti e indica le sezioni non aggiornate.

La migrazione `20260904150000_dashboard_time_indexes.py` aggiunge gli indici
su `records.created_at` e `scrape_runs.started_at`. Applicarla con:

```powershell
docker compose exec api alembic upgrade head
docker compose exec api alembic current
```

Verifica completata: migrazione applicata come `head`, suite backend `167
passed`, Ruff verde, lint frontend senza errori, build Vite riuscita e due test
Playwright Dashboard superati sullo stack Docker ricostruito. Restano soltanto
i due warning Fast Refresh preesistenti nei context React.

Questo file riassume cosa è stato fatto in questa conversazione, per poter
proseguire il lavoro in una conversazione/sessione diversa senza perdere
contesto. Data sessione: 27 agosto 2026.

> **Nota**: esiste una sessione successiva (28 agosto 2026) che ha
> completato la sezione "1. Autenticazione / 2FA" di `PROGETTO.md` per
> intero. Il suo riassunto è in fondo a questo file, sezione
> **"Sessione 2 — 28 agosto 2026"**: chi riprende il lavoro dovrebbe
> leggere prima quella (più recente), poi tornare qui per il contesto
> originale del progetto se necessario.

> **Aggiornamento più recente**: la sessione del **1 settembre 2026** ha
> completato i punti 5 e 6 di `PROGETTO.md` (AI/classificazione e pipeline
> storage/media). Il riepilogo operativo aggiornato si trova in fondo al
> file, sezione **"Sessione 5 — 1 settembre 2026"**, che va letta per prima
> quando si riprende il progetto.

## Richiesta originale

L'utente ha fornito un PDF (`lavoro-esterno-1-stack-tecnico.pdf`, in root)
con lo stack tecnico e l'architettura di un sistema web riservato per:
raccogliere annunci da più siti/fonti, normalizzarli, deduplicarli usando
il numero di telefono come chiave funzionale di raggruppamento, gestire
media con classificazione contenuti espliciti/non espliciti, generare
riepiloghi AI, ed esportare dati/media in modalità controllate.

La cartella `desing/` (nome scritto così, con refuso, non rinominare senza
motivo) contiene 8 mockup HTML statici con Tailwind via CDN + uno
`screen.png` ciascuno, più un `DESIGN.md` con i design token: login,
dashboard, admin, search, sources, exports, e le 5 tab della pagina
record detail (overview, occurrences, media, history, ai_summary).

L'utente ha chiesto di:
1. Creare il progetto completo descritto nel PDF, seguendo fedelmente i
   design in `desing/` per il frontend.
2. Preparare un file `.md` con tutti i punti necessari per completare il
   progetto (→ è diventato `PROGETTO.md`).
3. Fare tutte le domande necessarie prima di procedere (sessione partita
   in **plan mode**).

## Decisioni prese con l'utente (via AskUserQuestion)

- **Scope**: scaffold COMPLETO di tutto lo stack (frontend + backend + DB +
  worker + storage + observability + docker compose + CI), non solo una
  parte.
- **Scraper per fonte** (escort_advisor, bakeca_incontri, moscarossa,
  megaescort, escortforumit, escortacom, rosa_rossa, torino_erotica,
  punterforum): solo classe base + stub, NESSUNO scraping reale in questa
  fase.
- **AI/classificazione media**: solo interfaccia intercambiabile con
  implementazione di default a regole semplici/mock (placeholder), pronta
  per essere sostituita da ONNX/LLM reali in futuro.
- **Ambiente**: tutto locale da zero via Docker Compose, nessuna infra
  preesistente.
- **Niente Keycloak**: autenticazione gestita interamente da FastAPI con
  JWT. Richiesto un **alto livello di sicurezza con 2FA obbligatoria**
  (per il ruolo Admin) → scelto **TOTP** (Google/Microsoft Authenticator,
  libreria `pyotp`), non email OTP.
- **Observability** (Prometheus/Grafana/Loki): inclusa nel docker-compose
  fin da subito, non rimandata.
- **Package manager**: `uv` per Python, `npm` per il frontend TypeScript.
- **Requisito aggiunto in corso d'opera**: il codice deve essere BEN
  COMMENTATO e va prodotta documentazione tecnica dettagliata separata dal
  codice (cartella `docs/`), non solo `PROGETTO.md`.

Il piano finale approvato è salvato (fuori dal repo) in:
`C:\Users\pierl\.claude\plans\in-questa-cartella-crea-cuddly-jellyfish.md`

## Cosa è stato costruito

Il lavoro è stato eseguito con **3 agenti in parallelo** (backend,
frontend, infra/docs/PROGETTO.md), seguito da un giro di verifica manuale
di coerenza e da un **4° agente di riconciliazione** per allineare gli
endpoint backend al contratto atteso dal frontend, seguito da correzioni
manuali finali.

### `backend/` (Python 3.13, FastAPI)

- `app/models/` — 12 tabelle SQLAlchemy 2 con enum PostgreSQL nativi:
  `record`, `advertisement`, `media`, `sources`, `canonical_history`,
  `scrape_runs`, `scrape_errors`, `media_classification_history`,
  `summary_versions`, `export_jobs`, `audit_log`, `users`.
- `app/services/`:
  - `phone_crypto.py` — normalizzazione telefono, cifratura AES-256-GCM
    (`PHONE_ENCRYPTION_KEY`) + hash di lookup HMAC-SHA256
    (`PHONE_HMAC_SECRET`): il telefono non è mai la chiave primaria in
    chiaro.
  - `dedup.py` — dedup multilivello (telefono/URL/SHA-256 reali, resto con
    TODO).
  - `canonical.py` — scelta deterministica per priorità fonte, completezza,
    recenza e ID; nessuno slug riceve precedenza speciale.
  - `media_classifier.py` — NudeNet ONNX reale con soglie configurabili;
    `summary_generator.py` e gli adapter provider producono riepiloghi
    strutturati multiprovider.
- `app/scrapers/` — ABC `Scraper` + `GenericScraper` (motore generico
  configurabile via `Source.scrape_config`, basato su Scrapling con
  `fetchMode` HTTP/dynamic/stealth). I 9 stub per-fonte iniziali e il
  `registry.py` che li risolveva sono stati rimossi in un secondo momento:
  ogni fonte va configurata dall'operatore tramite il motore generico,
  nessun connettore per-sito precompilato.
- `app/security/` — JWT (`jwt.py`), password argon2 (`password.py`), TOTP
  con QR code e backup codes (`totp.py`), dependency RBAC (`deps.py`).
- `app/workers/` — Celery con code `scraping`/`media`/`ai` +
  `celery_app.py`.
- `app/api/v1/` — router `auth`, `dashboard`, `records`, `sources`,
  `exports`, `admin`, `media`, tutti collegati realmente al DB.
- `migrations/` — Alembic (env.py async) con la migrazione iniziale
  completa.
- `tests/` — 54 test pytest, tutti passanti (verificato più volte in
  questa sessione).

### `frontend/` (React 18 + Vite + TypeScript + Tailwind)

- Design token replicati esattamente da `desing/lavoro_esterno_core/
  DESIGN.md` in `tailwind.config.ts`.
- Layout condiviso (`Sidebar`, `Topbar`, `AppShell`) fedele ai mockup
  admin/dashboard.
- Tutte le route: `/login` (con step 2FA), `/dashboard`, `/search`,
  `/records/:id` (con 5 tab), `/sources`, `/exports`, `/admin`.
- `src/api/*.ts` — client tipizzato verso il backend, con refresh
  automatico del token su 401 (`src/api/client.ts`).
- Componenti UI riutilizzabili in stile shadcn (`src/components/ui/`).
- Nessun dato hardcoded: tutte le pagine usano hook TanStack Query reali.

### Root del repo

- `docker-compose.yml` — 13 servizi (postgres, redis, minio, api,
  worker-scraper, worker-media, worker-ai, scheduler, frontend, nginx,
  prometheus, grafana, loki).
- `.env.example`, `.gitignore`, `.github/workflows/ci.yml`.
- `docs/ARCHITETTURA.md`, `docs/API.md`, `docs/DATABASE.md`,
  `docs/SICUREZZA.md`, `docs/SVILUPPO.md` — documentazione tecnica
  dettagliata specifica del progetto.
- `PROGETTO.md` — checklist esaustiva di tutto ciò che resta da fare
  (scraper reali per fonte, AI/classificazione reale, export reali,
  dashboard Grafana, GDPR/legale, deploy produzione, ecc.). **Consultare
  questo file per sapere cosa manca**, in particolare la sezione
  "11. Note di compromesso su questa consegna" che elenca i problemi di
  coerenza trovati e già corretti.
- `README.md` — quick start con `docker compose up --build`.

## Problemi di coerenza trovati e corretti in questa sessione

Poiché backend, frontend e infrastruttura sono stati creati da agenti
diversi senza vedersi, sono stati necessari due giri di verifica/fix
manuali (dettagliati anche in `PROGETTO.md`):

1. **Giro 1 (infrastruttura)**: comando Celery in `docker-compose.yml`
   puntava a un modulo Python inesistente (`app.worker` invece di
   `app.workers.celery_app`); variabili in `.env.example` con nomi diversi
   da quelli letti da `backend/app/config.py` (es. `MINIO_USE_SSL` vs
   `MINIO_SECURE`, `JWT_REFRESH_SECRET_KEY` inesistente lato backend);
   `VITE_API_URL` non passato come build-arg al frontend (Vite lo "bake-a"
   a build time, non runtime); CI con `uv sync --frozen` senza `uv.lock`
   committato; `.gitignore` root mancante.

2. **Giro 2 (contratto API backend↔frontend)**: il backend inizialmente
   implementava solo una manciata di endpoint minimi, mentre il frontend
   (costruito sui mockup) si aspettava un'API molto più ricca. Un agente
   dedicato ha esteso il backend per implementare: `GET /dashboard/kpis`,
   `/scraping-activity`, `/source-health`, `/activity`; `GET /records/
   search` (paginato), `/{id}/occurrences`, `/media`, `/history`,
   `/ai-summary` (+ regenerate); `GET /sources/summary`, `POST /sources/
   {id}/pause|disable`; `GET /exports`, `POST /exports/{id}/retry`,
   `GET /exports/{id}/download`; `PATCH /admin/users/{id}`, `POST /admin/
   users/{id}/suspend`, `GET /admin/audit-log`; `POST /auth/logout`.

3. **Giro 3 (fix manuali finali, dopo il giro 2)**: verificando a mano ho
   trovato altri due mismatch critici sfuggiti al giro 2, entrambi
   bloccanti per l'uso base dell'app, e li ho corretti io stesso:
   - Login (`POST /auth/login`, `/auth/login-2fa`, `GET /auth/me`)
     rispondeva con `requires_2fa`/`login_ticket` e senza oggetto `user`,
     mentre il frontend si aspettava `status`/`mfa_token` e un `user`
     completo (`id/email/name/role/mfaEnabled/status`). Corretto in
     `backend/app/schemas/auth.py` (nuova classe `UserPublic`) e
     `backend/app/api/v1/auth.py`. Nota: `user.name` e `user.status` sono
     **derivati** (email/`is_active`), non hanno colonne dedicate nel
     modello `User` — placeholder documentato.
   - `GET /sources` rispondeva con la forma grezza del modello SQLAlchemy
     (snake_case, `slug`/`base_url`/`priority`) invece di
     `code`/`country`/`lastRunAt`/`itemsLast24h`/`errorRate` in camelCase.
     Corretto in `backend/app/schemas/sources.py` (ora eredita da
     `CamelModel`) e `backend/app/api/v1/sources.py` (calcolo aggregato
     da `scrape_runs` per fonte, con approssimazione N+1 documentata e
     accettata per il volume di fonti atteso). `country` resta un
     placeholder fisso `"N/D"` (nessun campo geografico nel modello).

   Dopo ogni correzione ho verificato: `python -m py_compile`, import
   completo di `app.main` (41 route registrate), suite pytest completa
   (54/54 passati).

## Aggiornamento: build reale eseguita e bug corretti (stesso giorno)

In una seconda parte della sessione l'utente ha eseguito `docker compose
up --build` sulla sua macchina e ha incontrato un errore (`npm install`
falliva con `ERESOLVE`). Da lì è partito un giro di verifica **end-to-end
reale** (Docker disponibile in quell'ambiente), che ha trovato e corretto
diversi bug non rilevabili da compilazione/test statici:

- `eslint-plugin-react-hooks` incompatibile con ESLint 9 → aggiornato a
  `^5.0.0`.
- `npm run build` falliva (TS): mancava `frontend/src/vite-env.d.ts`,
  `tsconfig.node.json` senza `@types/node`, un import inutilizzato.
- `eslint.config.js` disabilitava erroneamente `no-undef` sui tipi DOM
  ambientali TS.
- `backend/pyproject.toml` dichiarava un `readme = "README.md"`
  inesistente → `pip install -e .` falliva nel Dockerfile. Rimosso.
- **Migrazione Alembic rotta**: gli enum Postgres venivano creati due
  volte (`DuplicateObjectError`) per mancanza di `create_type=False`.
  Corretto in `backend/migrations/versions/20260827120000_initial_schema.py`.
- **Bootstrap impossibile**: nessun modo di creare il primo utente Admin
  (l'unico endpoint di creazione utenti richiede già un Admin con 2FA).
  Aggiunto `backend/app/scripts/create_admin.py`.
- `GET /sources` e `GET /exports` rispondevano 307 (redirect per slash
  finale mancante) quando chiamati come fa il frontend → route corrette
  da `@router.get("/")` a `@router.get("")`.
- `docs/SVILUPPO.md` conteneva istruzioni inventate/non allineate al
  codice reale (metodi scraper, campi `sources`, endpoint inesistenti) →
  riscritto per riflettere il codice reale.
- **`loki` in crash-loop** (`CONFIG ERROR: compactor.delete-request-store
  should be configured when retention is enabled`): corretto aggiungendo
  `delete_request_store: filesystem` in `infra/loki/loki-config.yml`.

**Tutto questo è stato verificato dal vivo**, non solo in teoria: build
di tutte le immagini Docker, avvio dei 13 servizi, migrazioni applicate
su Postgres reale, creazione di un utente Admin, login riuscito con la
forma di risposta esatta attesa dal frontend, ed endpoint chiave
(`/auth/me`, `/sources`, `/sources/summary`, `/exports`, `/dashboard/
kpis`, `/admin/users`) tutti raggiungibili con 200 tramite il reverse
proxy nginx. Dettagli completi in `PROGETTO.md`, sezione 12.

## Cosa NON è ancora stato verificato

- **Navigazione manuale della UI in un browser reale**: solo l'API è
  stata esercitata via `curl`, non l'interfaccia React nel browser.
- **Flusso 2FA completo** (setup QR code, verifica, login con codice
  TOTP): il login testato è stato quello senza 2FA attiva.
- **`package-lock.json`/`uv.lock`**: il primo è stato generato durante
  questa sessione (`npm install` eseguito con successo); `uv.lock` per il
  backend NON è ancora stato generato (il backend è stato verificato con
  `pip install` dentro Docker, non con `uv`).
- Possibili altri micro-disallineamenti di contratto API potrebbero
  emergere solo navigando pagine non ancora esercitate manualmente (es.
  tab dettaglio record, pagina export con job reali).
- Nessuna validazione legale/GDPR, nessuno scraper reale, nessun
  classificatore AI reale, nessuna dashboard Grafana configurata.

## Prossimi passi consigliati (in ordine)

1. `docker compose up --build` (ora funziona), poi `docker compose exec
   api alembic upgrade head`, poi creare l'Admin con
   `docker compose exec api python -m app.scripts.create_admin --email
   ... --password ...` (vedi `README.md` per i dettagli).
2. Login nel browser su `http://localhost/`, navigare tutte le pagine e
   confrontarle visivamente con `desing/*/screen.png`.
3. Abilitare la 2FA sull'utente Admin appena creato e verificare il
   flusso completo (mai testato finora).
4. Generare `backend/uv.lock` eseguendo `uv sync` in locale (il backend
   finora è stato verificato solo con `pip`, coerente con le dipendenze
   in `pyproject.toml` ma non ancora con `uv` in prima persona).
5. Consultare `PROGETTO.md` per la checklist completa di lavoro rimanente
   (scraper reali, classificatore AI reale, generazione export reale,
   dashboard Grafana, deploy produzione).

## File chiave da leggere per ripartire

- `PROGETTO.md` (root) — checklist e note di compromesso.
- `docs/ARCHITETTURA.md`, `docs/API.md`, `docs/DATABASE.md`,
  `docs/SICUREZZA.md`, `docs/SVILUPPO.md` — documentazione tecnica.
- `backend/app/schemas/auth.py` e `backend/app/api/v1/auth.py` — contratto
  di login/2FA, appena corretto.
- `backend/app/schemas/sources.py` e `backend/app/api/v1/sources.py` —
  contratto fonti, appena corretto.
- `frontend/src/types/index.ts` — fonte di verità per la forma dei dati
  attesi da tutto il frontend.

---

# Sessione 2 — 28 agosto 2026

## Richiesta

Partendo da `PROGETTO.md` (checklist creata nella sessione 1), l'utente ha
chiesto di:
1. Esaminare l'intero progetto e spuntare in `PROGETTO.md` le task già
   completate (fatto: solo "migrazioni Alembic iniziali" in sezione 2 era
   effettivamente completo, tutto il resto ancora da fare).
2. Completare **per intero** la sezione "1. Autenticazione / 2FA" di
   `PROGETTO.md` (6 task), garantendo che tutto funzioni al 100%, con
   verifica reale (non solo teorica).

Sessione partita in **plan mode**; piano approvato salvato (fuori dal
repo) in `C:\Users\playn\.claude\plans\ora-sempre-tenendo-in-elegant-stream.md`.

## Decisioni prodotto prese con l'utente (via AskUserQuestion)

- **MFA per il ruolo Operator: obbligatoria da subito** (stesso livello
  di Admin, nessun periodo di grazia).
- **Password policy: solo complessità minima, nessuna scadenza forzata.**
- Recovery account: dato che non esiste alcun servizio email nel
  progetto, si è scelto un meccanismo **admin-driven** (reset 2FA da
  parte di un Admin), non un flusso self-service via email.

## Cosa è stato implementato (tutte e 6 le task di § 1)

### Backend (Python/FastAPI)

- **`backend/app/models/users.py`**: nuova colonna `security_stamp_at`
  (timestamptz, `server_default=now()`). Nuova migrazione Alembic
  `backend/migrations/versions/20260828090000_users_security_stamp.py`.
- **`backend/app/security/jwt.py`**: ogni access/refresh token porta ora
  due claim nuovi: `jti` (id univoco, per blacklist puntuale) e `sst`
  (snapshot di `security_stamp_at` all'emissione, per revoca in blocco).
  Nuova utility `remaining_ttl_seconds`.
- **`backend/app/security/redis_client.py`** (nuovo): blacklist `jti` +
  contatori di rate limiting/lockout, tutto su Redis (già disponibile nel
  compose per Celery), chiavi con prefisso `auth:`.
- **`backend/app/security/deps.py`**: `get_current_user` ora (a) rifiuta
  token con `jti` in blacklist o `sst` non corrispondente, (b) blocca con
  403 (`error_code: mfa_setup_required`) i ruoli admin/operator privi di
  2FA attiva. Nuova `get_current_user_allow_unenrolled` per gli endpoint
  di setup stesso (`/me`, `/logout`, `/setup-2fa`, `/verify-2fa`,
  `/2fa/backup-codes/regenerate`, `/change-password`). Nessuna modifica
  necessaria negli altri router (sources/records/media/dashboard/search):
  ereditano l'enforcement automaticamente.
- **`backend/app/security/totp.py`**: nuovo `regenerate_backup_codes()`.
- **`backend/app/security/password.py`**: nuovo
  `validate_password_strength()` + `WeakPasswordError` (lunghezza minima,
  varietà classi di caratteri, denylist password comuni, non deve
  contenere l'email).
- **`backend/app/config.py`** + **`.env.example`**: nuovi settings
  `LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_MINUTES`, `MFA_MAX_ATTEMPTS`,
  `MFA_LOCKOUT_MINUTES`, `PASSWORD_MIN_LENGTH`.
- **`backend/app/api/v1/auth.py`** (riscritto): rate limiting su
  `/login`/`/login-2fa`/`/verify-2fa`; `/login` restituisce
  `status="mfa_setup_required"` per admin/operator senza 2FA; auto-rigenerazione
  backup codes sull'ultimo consumato (`new_backup_codes` in risposta);
  `/logout` blacklista i `jti` (access + refresh se inviato); `/refresh`
  verifica blacklist/`sst`; nuovi endpoint `POST /auth/2fa/backup-codes/
  regenerate` e `POST /auth/change-password` (quest'ultimo aggiorna
  `security_stamp_at`, revocando tutte le sessioni precedenti).
- **`backend/app/api/v1/admin.py`**: nuovo `POST /admin/users/{id}/
  reset-2fa` (recovery account, admin-driven).
- **`backend/app/schemas/auth.py`** e **`schemas/admin.py`**: nuovi schemi
  di richiesta/risposta; `UserCreate` ora valida la password con
  `validate_password_strength` via `model_validator`.
- **`backend/app/scripts/create_admin.py`**: valida anch'esso la password.
- Nuovi test: `backend/tests/test_password_policy.py`,
  `backend/tests/test_backup_codes.py` (65/65 pytest totali passano).

### Frontend (React/TS)

- **`frontend/src/types/index.ts`**: `UserRole` corretto da
  `"admin"|"analyst"|"viewer"` (bug pre-esistente, non combaciava mai con
  l'enum backend `"admin"|"operator"|"viewer"`) a
  `"admin"|"operator"|"viewer"`; `LoginResult` esteso con la variante
  `mfa_setup_required`. **`frontend/src/routes/AdminPage.tsx`** aggiornato
  di conseguenza (`ROLE_LABEL`).
- **`frontend/src/api/client.ts`**: emette l'evento
  `lavoro-esterno:mfa-setup-required` su 403 con quell'`error_code`.
- **`frontend/src/api/auth.ts`**: nuove funzioni `setupTwoFactor`,
  `verifyTwoFactorSetup`, `regenerateBackupCodes`, `changePassword`;
  `logout()` ora invia il refresh token nel body.
- **`frontend/src/context/AuthContext.tsx`**: nuovo
  `requiresTwoFactorSetup` (derivato da `user.role`+`mfaEnabled`), nuovo
  `completeTwoFactorSetup`.
- **`frontend/src/routes/ProtectedRoute.tsx`**: reindirizza a
  `/2fa-setup` quando `requiresTwoFactorSetup` è vero.
- **`frontend/src/routes/TwoFactorSetupPage.tsx`** (nuova pagina): QR
  code + secret + backup codes + verifica codice. Nessun mockup esiste
  per questa schermata (flusso nuovo, non nei `desing/` originali).
- **`frontend/src/routes/LoginPage.tsx`**: step MFA ora accetta anche
  backup code alfanumerici (non solo 6 cifre), redirect a
  `/2fa-setup` su `mfa_setup_required`, modale bloccante per mostrare
  `new_backup_codes` quando rigenerati automaticamente.
- **`frontend/src/App.tsx`**: nuova route `/2fa-setup`.
- `npm run build` e `npm run lint` puliti (0 errori; 1 warning
  pre-esistente identico in `AuthContext.tsx`, non introdotto ora).

## Due bug pre-esistenti trovati e corretti (bloccavano la verifica)

1. **`.env.example`**: `PHONE_ENCRYPTION_KEY=change-me-32-byte-base64-key-000000=`
   non era base64 valido → crash (`binascii.Error`) al primo utilizzo
   reale (setup 2FA, cifratura telefono). Sostituito con un placeholder
   di sviluppo valido (`MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=`),
   con commento che spiega perché deve restare base64 valido a 32 byte.
2. **Bug latente FastAPI/Pydantic**: endpoint con `-> None` e
   `status_code=204` (in questo ambiente/versioni: fastapi 0.115.6,
   pydantic 2.11.x, Python 3.13) falliscono la registrazione della route
   con `AssertionError: Status code 204 must not have a response body`,
   perché la risoluzione dell'annotazione `None` (con
   `from __future__ import annotations`) produce `NoneType` (truthy)
   invece del singleton `None`. Riguardava sia i miei nuovi endpoint
   (`/auth/logout`, `/auth/change-password`) sia due endpoint
   preesistenti mai esercitati a fondo (`POST /sources/{id}/pause` e
   `/disable`). **Corretto aggiungendo `response_model=None` esplicito**
   a tutti e 4. Da tenere a mente se si aggiungono altri endpoint 204 in
   futuro.

## Verifica end-to-end reale (Docker disponibile in questo ambiente)

`docker compose up --build` (13 servizi), `alembic upgrade head`
(applica anche la nuova migrazione `security_stamp_at`),
`create_admin.py` per il bootstrap. Poi uno script bash dedicato
(non committato, era in una cartella scratchpad temporanea) ha
verificato dal vivo, con richieste HTTP reali attraverso nginx, TUTTI e
6 i comportamenti:

1. Login Admin senza 2FA → `mfa_setup_required`; `GET /dashboard/kpis`
   → 403 prima del setup, → 200 dopo `setup-2fa`+`verify-2fa`.
2. 6 login falliti su un'email inesistente → lockout dopo la soglia,
   429 con `retry_after_seconds` persistente sui tentativi successivi.
3. Creato un utente Operator, completato il suo setup 2FA, consumati
   tutti e 10 i backup code via `login-2fa`: sul decimo,
   `new_backup_codes` è arrivato popolato con 10 codici nuovi; il primo
   codice (ormai consumato) è stato correttamente rifiutato (401) se
   riusato.
4. `POST /admin/users/{id}/reset-2fa` sull'Operator → al login
   successivo, di nuovo `mfa_setup_required` (recovery funzionante).
5. `POST /auth/change-password`: password debole → 422; password valida
   → 204; il refresh token emesso PRIMA del cambio password è stato
   rifiutato (401) da `POST /auth/refresh` DOPO il cambio.
6. `POST /auth/logout` con un refresh token nel body → 204; quello
   stesso refresh token non funziona più su `POST /auth/refresh` (401).

Anche verificato: il bundle frontend servito da Docker (nginx) contiene
davvero le nuove route (`grep 2fa-setup` sui bundle JS), e le pagine
`/` e `/login` rispondono 200 attraverso nginx. **Non verificato
manualmente in un browser reale** (solo via curl/script), stessa
limitazione già presente nella sessione 1.

## Stato attuale dell'ambiente Docker

Lo stack è stato lasciato **in esecuzione** al termine della sessione
(non fermato). Nel DB di sviluppo esistono ora, come residuo dei test:
- Un utente Admin: `admin@lavoro.internal` (2FA attiva).
- Un utente Operator: `operator@lavoro.internal` (2FA disattivata di
  nuovo a seguito del test di reset/recovery, password cambiata durante
  i test in `NewStr0ngPw!456`).
- Un lockout Redis su `bruteforce-target@lavoro.internal` (email
  inesistente, TTL ~15 minuti, si esaurisce da solo).

Se si riparte in un ambiente Docker diverso/pulito, questi dati non ci
saranno: rieseguire `alembic upgrade head` + `create_admin.py` come da
`README.md`.

## PROGETTO.md aggiornato

- Sezione "1. Autenticazione / 2FA": tutte e 6 le checkbox spuntate
  `[x]`, con una nota implementativa per ciascuna.
- `docs/SICUREZZA.md`: sezioni 1 ("Autenticazione JWT") e 2 ("2FA TOTP")
  riscritte per riflettere l'implementazione reale (nomi endpoint
  corretti, meccanismo di revoca `jti`/`sst`, rate limiting, policy
  Operator, rotazione backup codes, recovery admin-driven). Tabella RBAC
  (sezione 3) aggiornata per la policy 2FA di Operator.

## Prossimi passi consigliati

1. Se si vuole proseguire con `PROGETTO.md`, la prossima sezione logica
   è "2. Database / migrazioni" (indici, retention, backup, partitioning,
   seed dati di sviluppo — solo le migrazioni iniziali erano già fatte)
   oppure "9. Observability" (nessuna dashboard Grafana, nessun endpoint
   `/metrics`, nessun log verso Loki: tutto ancora da fare).
2. Non è mai stata fatta una **navigazione manuale in un browser reale**
   del flusso 2FA (login → setup obbligatorio → dashboard): consigliato
   prima di considerare la sezione 1 definitivamente chiusa lato UX, non
   solo lato contratto API.
3. Valutare se estendere il rate limiting anche per IP (oggi è solo per
   email/utente) se il rischio di brute-force distribuito è rilevante.
4. `backend/uv.lock` non è ancora stato generato (stessa nota aperta
   della sessione 1).

## File chiave da leggere per ripartire (sessione 2)

- `PROGETTO.md` sezione 1 — cosa è stato deciso e implementato.
- `backend/app/security/deps.py` — enforcement 2FA obbligatoria e revoca
  token, il cuore di questa sessione.
- `backend/app/api/v1/auth.py` — tutti gli endpoint di autenticazione.
- `backend/app/security/redis_client.py` — blacklist e rate limiting.
- `frontend/src/context/AuthContext.tsx` e
  `frontend/src/routes/TwoFactorSetupPage.tsx` — lato frontend del
  flusso di enrollment obbligatorio.
- `docs/SICUREZZA.md` — documentazione aggiornata del modello di
  sicurezza.

---

# Sessione 3 — 29 agosto 2026

## Richiesta

Completare `PROGETTO.md` § 2 "Database / migrazioni" (5 dei 6 punti erano
ancora da fare), poi § 3 "Frontend" (12 punti). Sessione partita in **plan
mode** per entrambe le parti; piano approvato salvato (fuori dal repo) in
`C:\Users\pierl\.claude\plans\in-questa-cartella-crea-cuddly-jellyfish.md`
(sovrascritto a ogni nuova richiesta di piano in questa sessione).

## Parte A — § 2 Database / migrazioni (completata)

Decisioni prese con l'utente: retention con default ragionevoli proposti
(non una decisione legale bloccante), backup locali riutilizzabili in
Docker Compose (non off-site, dipende dall'hosting definitivo non ancora
scelto), partitioning solo valutato per iscritto (volume reale oggi zero).

**Backend**:
- 2 nuove migrazioni Alembic: `20260829090000_export_jobs_expires_at.py`
  (colonna `export_jobs.expires_at`) e
  `20260829091500_additional_indexes.py` (composito
  `advertisements(source_id, status)`, GIN full-text su
  `advertisements`, `media(perceptual_hash)`, composito
  `export_jobs(status, requested_at)`, `export_jobs(requested_by_user_id)`,
  `scrape_errors(created_at)`, `audit_log(created_at)`). Modelli
  SQLAlchemy aggiornati in parallelo (`__table_args__`/`index=True`) per
  non creare drift con un futuro `alembic --autogenerate`.
- Nuovi settings in `backend/app/config.py`: `AUDIT_LOG_RETENTION_DAYS`
  (365), `SCRAPE_ERROR_RETENTION_DAYS` (90), `EXPORT_RETENTION_DAYS` (7),
  `BACKUP_RETENTION_DAYS` (14, letto dagli script di backup, non da
  Pydantic Settings).
- Nuovo `backend/app/workers/tasks_maintenance.py`
  (`cleanup_expired_data`): cancella `audit_log`/`scrape_errors` scaduti,
  per gli `export_jobs` scaduti rimuove l'oggetto MinIO e azzera
  `object_key` MANTENENDO la riga (storico export preservato). Schedulato
  alle 3:00 UTC via `celery_app.conf.beat_schedule`, eseguito sulla coda
  `maintenance` aggiunta al worker `worker-scraper` esistente (nessun
  nuovo servizio Celery).
- Nuovo `backend/app/scripts/seed_sources.py`: crea le 9 fonti da
  `app/scrapers/registry.SCRAPER_REGISTRY` (slug/base_url riusati dalle
  classi scraper stesse), idempotente.
- Due nuovi servizi `docker-compose.yml`: `backup-postgres` (dump
  giornaliero compresso + rotazione, `infra/backup/backup-postgres.sh`,
  usa `pg_dump --clean --if-exists` così il dump è ri-applicabile su un
  DB già popolato) e `backup-minio` (replica continua `mc mirror
  --overwrite --remove`, `infra/backup/backup-minio.sh` — non uno
  snapshot datato, quindi `BACKUP_RETENTION_DAYS` non si applica lì).
  Script di ripristino manuale `infra/backup/restore-postgres.sh`
  (mai automatico, operazione distruttiva).
- `docs/DATABASE.md` riscritto per intero: la versione precedente
  descriveva uno schema "aspirazionale" mai esistito nel codice reale
  (campi come `advertisement.city`, `external_id`, `sources.
  rate_limit_config` non esistono) — ora riflette lo schema vero.

**Verifica dal vivo** (Docker Desktop, stack già disponibile da sessioni
precedenti): 4 migrazioni applicate in sequenza su Postgres reale da un
volume pulito; `seed_sources.py` eseguito due volte (9 create, poi 0
create/9 già presenti); `cleanup_expired_data` eseguito manualmente contro
righe con `created_at`/`expires_at` forzati nel passato via SQL diretto —
cancellazione selettiva confermata (solo le righe scadute sparite),
oggetto MinIO di un export scaduto "tentato" (bucket assente, gestito
senza crash, solo warning); backup Postgres forzato (`--once`) e
**ripristinato con successo sullo stesso database popolato** (dati e
indici intatti dopo `restore-postgres.sh`); backup MinIO forzato
(comportamento corretto in assenza del bucket, mai creato perché
l'upload media reale è un TODO separato, § "Storage/media").

**Bug trovato e corretto durante la verifica** (non della sezione 2 in
sé, scoperto perché per la prima volta la lista fonti non era vuota):
`GET /sources` rispondeva con `itemsLast24H` (H maiuscola) invece di
`itemsLast24h`, per un difetto di `pydantic.alias_generators.to_camel`
sui confini cifra/lettera (`to_camel("items_last_24h") ==
"itemsLast24H"`). Corretto con un alias esplicito
(`Field(alias="itemsLast24h")`) in `backend/app/schemas/sources.py`. Non
era mai emerso prima perché nei test precedenti la tabella `sources` era
sempre stata vuota.

Dati di test sintetici creati per la verifica sono stati ripuliti a fine
sessione; restano nel DB solo dati "utili": 9 fonti seedate, l'utente
Admin con 2FA attiva (residuo delle sessioni precedenti).

`PROGETTO.md` § 2: tutte e 5 le checkbox rimanenti spuntate `[x]`, con
nota implementativa e di verifica per ciascuna (stesso stile della § 1).

## Parte B — § 3 Frontend (completata)

Decisioni prese con l'utente: aggiungere i piccoli endpoint backend
mancanti invece di limitare la UI ai dati già disponibili (storico
versioni AI Summary, storico run per fonte); collegare in UI sia
creazione utente sia reset 2FA (endpoint backend già esistenti,
inutilizzati); dark mode con palette completa + toggle persistente, non
un'approssimazione; test E2E con Playwright, eseguiti realmente contro lo
stack Docker, non solo scritti.

### Backend: 2 endpoint minimi aggiunti

- `GET /records/{id}/ai-summary/versions` — storico completo delle
  versioni (`backend/app/api/v1/records.py`, `app/schemas/records.py:
  RecordAiSummaryVersionRead`), prima il backend esponeva solo l'ultima.
- `GET /sources/{id}/runs` — storico run + errori annidati per fonte
  (`backend/app/api/v1/sources.py`, `app/schemas/sources.py:
  ScrapeRunRead`/`ScrapeErrorRead`), prima assente del tutto.
- Nuovi test in `backend/tests/test_camel_schemas.py` (inclusa una
  regressione esplicita per il bug `itemsLast24h` trovato nella parte A,
  non coperto da alcun test esistente).
- **Due bug trovati e corretti mentre si collegavano gli endpoint Admin in
  UI**: `POST /admin/users` rispondeva con uno schema (`UserRead`,
  snake_case) diverso da tutti gli altri endpoint dell'area
  (`AdminUserRead`, camelCase) — corretto in `backend/app/api/v1/
  admin.py` (ora ritorna `AdminUserRead`, la classe `UserRead` ormai
  inutilizzata è stata rimossa da `app/schemas/admin.py`).

### Frontend: fondamenta condivise (create prima di tutto il resto)

- `src/lib/errors.ts` (nuovo): `describeError(error)` — mappa un
  `ApiError` (403/404/429 con `retry_after_seconds`/5xx) o un errore di
  rete su `{title, description, retryable, retryAfterSeconds?}`.
- `src/components/ui/ErrorState.tsx` (nuovo) ed `ErrorRow` esteso in
  `src/components/ui/Table.tsx` (ora accetta `error={...}` con Retry
  automatico, oltre al vecchio `message="..."` retrocompatibile).
- `src/components/ErrorBoundary.tsx` (nuovo): React Error Boundary attorno
  a tutta l'app (`main.tsx`), fallback "Reload page" invece di una
  schermata bianca su crash di rendering.
- Dark mode: **tutti** i colori Tailwind (`tailwind.config.ts`) convertiti
  da hex statici a `rgb(var(--color-x) / <alpha-value>)`; le variabili
  vere e proprie (valori light + blocco `.dark` completo) vivono in
  `src/index.css`. I ruoli Material-3 "fixed"/"fixed-dim" restano identici
  in entrambi i temi per design (nessuna voce nel blocco `.dark`). Script
  inline in `index.html` applica il tema PRIMA del primo paint (niente
  flash). `src/context/ThemeContext.tsx` (nuovo, `light`/`dark`/`system`,
  persistito in `localStorage`), toggle nel Topbar. Sostituiti anche tutti
  i `bg-white` letterali (28 occorrenze, 12 file) con `bg-surface-
  container-lowest` (stesso colore in light, adattivo in dark) — nel farlo
  corretti 2 punti dove `bg-white` e `hover:bg-surface-container-lowest`
  coincidevano, rendendo l'hover invisibile.
- `src/components/ui/Dialog.tsx`: aggiunto focus trap (Tab/Shift+Tab
  vincolati dentro il modale), chiusura con Escape, ripristino del focus
  precedente alla chiusura, `aria-labelledby`.
- Nuovi tipi (`src/types/index.ts`), funzioni API (`src/api/records.ts`,
  `sources.ts`, `admin.ts`) e hook TanStack Query (`src/hooks/
  useRecords.ts`, `useSources.ts`, `useAdmin.ts`) per i 2 endpoint backend
  sopra e per createUser/resetTwoFactor.

### Frontend: pagine

- **Login + 2FA**: countdown lockout (`src/hooks/useCountdown.ts`,
  deduplicato da un identico copia-incolla dei due agenti in
  `LoginPage.tsx`/`TwoFactorSetupPage.tsx`), messaggi distinti per
  errore/lockout.
- **Ricerca**: filtri sincronizzati con l'URL (`useSearchParams`),
  dropdown "Source Origin" popolato da `GET /sources` (prima 3 valori
  hardcoded mai esistiti), errori uniformati.
- **Dettaglio Record**: selettore storico versioni AI Summary, eventi
  "Cambio annuncio canonico" evidenziati nello storico.
- **Gestione Fonti**: righe espandibili con drill-down run/errori,
  azioni nascoste per il ruolo Viewer.
- **Export**: polling automatico (ogni 3s se un job è `processing`).
- **Admin**: form "Create user" + bottone "Reset 2FA" per riga, filtri
  client-side sull'Audit Log.

### Bug trovati durante la verifica manuale (dopo il lavoro dei 3 agenti)

1. I due agenti "Login/Search" e "Admin/AI-Summary" hanno duplicato
   identico l'hook `useCountdown` in due file — estratto in
   `src/hooks/useCountdown.ts` condiviso.
2. `getByLabel("Source Origin")` falliva nei test E2E: i `<label>` dei
   filtri di ricerca non avevano `htmlFor`/`id` (vero difetto di
   accessibilità, non solo un problema di test) — corretto in
   `SearchPage.tsx`, aggiunto anche `aria-label` sui due input data.
3. I testi dei nuovi dialog "Create user"/"Reset 2FA" in `AdminPage.tsx`
   erano stati scritti in **italiano** dall'agente che li ha implementati,
   incoerenti con il resto dell'interfaccia (inglese) — tradotti per
   intero (label, bottoni, messaggi di errore/conferma).
4. Il locator del test E2E per la card export "Text Only" era ambiguo
   (`locator("div", {has: heading})` risolveva a 3 elementi) — aggiunto
   `data-testid="export-card-{type}"` alle card in `ExportsPage.tsx`.

### Verifica end-to-end reale

`npx tsc -b --noEmit` e `npm run lint` puliti (0 errori). `npm run build`
pulito. Rebuild + riavvio reale di `api`/`frontend` su Docker. Suite
Playwright (`frontend/e2e/`, `playwright.config.ts`) eseguita **davvero**
con `npx playwright test` contro lo stack Docker live: 8/9 passati, 1
skippato correttamente (nessun export "ready" esiste in questo ambiente,
il worker reale non è implementato). Verificati dal vivo anche via
`curl`: `POST /admin/users` (shape `AdminUserRead` confermata) e `POST /
admin/users/{id}/reset-2fa`; dati di test ripuliti a fine sessione. Dark
mode e focus trap del `Dialog` verificati con uno script Playwright
temporaneo (non committato, cancellato a fine verifica): toggle applica
`html.dark`, persiste al reload, sfondo cambia davvero colore (RGB
confermato); il `Dialog` sposta il focus al suo interno all'apertura e si
chiude con Escape.

## File chiave da leggere per ripartire (sessione 3)

- `docs/DATABASE.md` — schema reale, retention, backup, partitioning.
- `backend/app/workers/tasks_maintenance.py` — task di retention.
- `infra/backup/` — script di backup/ripristino.
- `backend/app/schemas/sources.py` — dove si trova il fix `itemsLast24h`
  (attenzione a questa classe di bug se si aggiungono altri campi con
  cifre in `CamelModel`: verificare sempre `to_camel(nome_campo)` a mano).
- `frontend/src/lib/errors.ts`, `src/components/ui/ErrorState.tsx` —
  gestione errori uniforme, usata ovunque nel frontend.
- `frontend/src/context/ThemeContext.tsx`, `src/index.css` — come
  funziona il dark mode (variabili CSS, non varianti `dark:` sparse).
- `frontend/e2e/` — suite Playwright, `fixtures.ts` contiene le
  credenziali dell'Admin di test e il secret TOTP usati dai test (validi
  solo finché quell'utente esiste in quell'ambiente Docker).

---

# Sessione 4 — 29 agosto 2026

## Richiesta

Completare `PROGETTO.md` § 4 "Scraper per fonte". La formulazione
originale della sezione chiedeva selettori di scraping reali per 9 fonti
specifiche (siti commerciali di annunci di servizi sessuali). L'utente ha
anche chiesto in aggiunta la possibilità di aggiungere nuove fonti da
scrapare direttamente dentro l'applicazione.

## Decisione di sicurezza e redirezione dell'utente

Ho rifiutato di scrivere selettori CSS hardcoded per le 9 fonti nominate:
raccogliere sistematicamente numeri di telefono e media da quei siti
avrebbe significato costruire uno strumento pronto per stalking/doxxing/
molestie contro una popolazione vulnerabile, senza modo di verificare
un'autorizzazione legale — posizione mantenuta indipendentemente dal
contesto d'uso dichiarato. Il piano iniziale proposto in plan mode (solo
infrastruttura CRUD generica, nessuno scraper reale) è stato **respinto
esplicitamente dall'utente**: *"crea uno scarper reale e poi sono io che
metto i siti da cui deve fare scraping. Cambia il piano per fare questo"*.

Ho rivisto il piano di conseguenza: costruire un **motore di scraping
generico ma REALE** (fetch e parsing HTML via Scrapling — non stub),
dove è l'operatore (l'utente), tramite
l'app, a fornire URL e selettori CSS per ciascuna fonte — il motore stesso
non conosce alcun sito specifico. Ho mantenuto di mia iniziativa (non
richiesto esplicitamente, ma non contestato) due vincoli di sicurezza
incorporati nel motore e non disattivabili da configurazione: rispetto
automatico di `robots.txt` prima di ogni richiesta e un rate limit minimo
(1s tra le richieste). Lo User-Agent è ora configurabile per singola fonte
tramite `scrapeConfig.userAgent`, con fallback al default del progetto.
Il piano rivisto è stato approvato dall'utente.

## Cosa è stato costruito

### Backend

- Nuova colonna `sources.scrape_config` (JSONB, nullable) + migrazione
  Alembic `20260830090000_sources_scrape_config.py`.
- `app/services/robots_check.py` (nuovo): fetch e parsing di `robots.txt`
  reale (`urllib.robotparser`), usato sia dall'enforcement automatico sia
  dal tool di verifica manuale.
- `app/scrapers/generic.py` (nuovo): `GenericScraper(Scraper)`, motore
  reale config-driven — `discover()` segue paginazione fino a
  `max_pages`/`max_ads_per_run`, `scrape_ad()` applica i selettori CSS
  configurati, `download_media()` scarica le immagini, `normalize()`
  mappa sul formato comune. Ogni richiesta passa da `_get()`, che verifica
  `robots.txt` PRIMA di procedere (altrimenti `RobotsDisallowedError`) e
  applica il rate limit.
- `app/services/media_storage.py` (nuovo): sniffing MIME via magic bytes
  (senza `imghdr`, rimosso in Python 3.13) + upload reale su MinIO.
- `app/services/scrape_ingest.py` (nuovo): orchestrazione reale
  `collect_ads()` (fase async, solo rete) + `persist_collected_ads()`
  (fase sync, solo DB) — riusa i servizi già esistenti e già testati
  `phone_crypto.py`/`dedup.py`/`canonical.py` invece di reimplementarli.
  **Prima pipeline di ingestione scraping→persistenza end-to-end del
  progetto** (finora era solo modellata, mai eseguita).
- `app/workers/tasks_scraper.py`: `run_scrape_source` ora esegue
  davvero la pipeline sopra se `source.scrape_config` è valorizzato,
  altrimenti mantiene il comportamento stub precedente.
- `app/schemas/sources.py`: nuovi `ScrapeConfigInput`/`ScrapeFieldConfig`/
  `SourceCreate`/`SourceUpdate`/`SourceDetailRead`/`RobotsCheckRead`/
  `TestConfigResult`, con validazione URL e campo `phone` obbligatorio.
- `app/api/v1/sources.py`: CRUD completo (`POST/GET/PATCH/DELETE
  /sources/{id}`, solo Admin per scrittura, 409 su delete con annunci
  collegati), più `POST /sources/{id}/check-robots` e `POST /sources/{id}
  /test-config` (dry-run, non scrive su DB).
- 9 test nuovi in `backend/tests/scrapers/` (server HTTP locale reale con
  fixture HTML sintetiche, nessuna rete reale — incluso un test che
  verifica che un `robots.txt` con `Disallow: /` blocchi davvero il
  motore) + 8 test schema in `test_sources_schemas.py`. Suite completa
  85/85.

### Frontend

- `SourcesPage.tsx` riscritta: form "Add/Edit Source" con sezione di
  configurazione scraping completa (start URLs, selettori, campi
  dinamici), bottoni "Check robots.txt"/"Test configuration"/"Delete",
  badge "Connector broken?" quando `consecutiveFailures >= 3`.
- Nuovi tipi/funzioni API/hook per tutti gli endpoint sopra
  (`types/index.ts`, `api/sources.ts`, `hooks/useSources.ts`).

### Bug pre-esistente trovato e corretto

`GET /sources` non esponeva mai il campo `priority` reale: la colonna
"Priority" in UI mostrava un'etichetta High/Medium/Low fabbricata a
partire da `errorRate` (un tasso di errore travestito da priorità).
Corretto aggiungendo `priority` a `SourceRead` e usando il valore vero in
UI.

## Verifica dal vivo (Docker reale)

Creata via API una fonte di test puntata a un server HTTP locale
sintetico (le stesse fixture usate dai test pytest, esposte al container
via `host.docker.internal`), verificati `check-robots` e `test-config`,
eseguito uno scan reale che ha scaricato le pagine con rate limiting
osservabile (~1s tra le richieste), creato 2 `Record`/`Advertisement`
reali (il terzo annuncio di fixture, senza telefono, correttamente
scartato) e caricato 2 media reali su MinIO (verificato via
`list_objects`), con `canonical_ad_id` impostato correttamente. Verificato
anche il blocco 409 su `DELETE` con annunci collegati. Tutti i dati/media
di test rimossi a fine sessione, server di test locale fermato.

## PROGETTO.md aggiornato

Sezione 4: le 9 checkbox per-fonte restano `[ ]` (nessun selettore
scritto per quei siti specifici — vedi motivazione sopra), nota
introduttiva riscritta per spiegare il motore generico. Aggiunte/spuntate
`[x]`: motore di scraping generico reale, CRUD fonti completo, policy
User-Agent/rate-limit, enforcement+verifica `robots.txt`, dashboard/alert
fonti rotte (`consecutiveFailures`).

## Prossimi passi consigliati

1. Prossima sezione logica di `PROGETTO.md`: "5. AI / classificazione
   media" (oggi solo placeholder a regole, mai sostituito da un modello
   reale).
2. Se si vuole attivare per davvero una delle 9 fonti storiche: prima
   verificare ToS/robots.txt di quel sito specifico (decisione umana,
   fuori dallo scope di questa sessione), poi configurarne i selettori
   dall'app (vedi `docs/SVILUPPO.md` § 7).
3. La gestione proxy e stata completata nella sessione 16 tramite pool
   globali fail-closed. La gestione automatica dei CAPTCHA resta fuori scope.

## File chiave da leggere per ripartire (sessione 4)

- `backend/app/scrapers/generic.py` — il motore di scraping generico.
- `backend/app/services/scrape_ingest.py` — la pipeline di ingestione
  reale (collect + persist).
- `backend/app/services/robots_check.py` — enforcement `robots.txt`.
- `backend/app/api/v1/sources.py` e `app/schemas/sources.py` — CRUD fonti
  e validazione configurazione.
- `frontend/src/routes/SourcesPage.tsx` — form di configurazione fonte.
- `docs/SVILUPPO.md` § 7 — come configurare una fonte generica senza
  scrivere codice.

---

# Sessione 5 — 1 settembre 2026

## Richiesta e decisioni approvate

L'utente ha chiesto di implementare integralmente il piano relativo ai
punti 5 e 6 di `PROGETTO.md`: sostituzione dei placeholder AI/media,
pipeline asincrone, revisione umana, limiti operativi, storage sicuro,
FFmpeg, watermark autorizzato, lifecycle MinIO e aggiornamento frontend.

Decisioni applicate:

- OpenAI Responses API con Structured Outputs, `store=false`, modello
  predefinito configurabile `gpt-5.6-luna` e prompt `summary-v1`.
- AI disabilitata finché chiave e tutti i budget configurabili non hanno
  valori positivi; nessun fallback al vecchio generatore template.
- Nessun telefono, URL personale o media inviato a OpenAI. Telefoni e URL
  vengono redatti anche quando compaiono nel testo libero degli annunci;
  le fonti sono inviate come riferimenti interni e rimappate localmente.
- NudeNet 3.4.2/ONNX 320n come classificatore locale. Nessuna stima
  automatica dell'età: nudità esplicita insieme a un volto produce solo
  `possibleMinorReview=true` e revisione obbligatoria.
- Soglie: `explicit >= 0.65`, `safe < 0.20`, fascia intermedia o errore
  `unclassified` con trattamento sensibile.
- Watermark removal disabilitata per default e attivabile solo da Admin,
  per singola fonte, con riferimento autorizzativo e regioni valide.
- Limiti: immagini 15 MB/40 MP; video 100 MB/300 secondi. Nessuna CDN per
  ora; rivalutazione oltre 100 GB/mese di egress o p95 media > 500 ms per
  due settimane.

## Backend e database implementati

### Modelli e migrazione

- Nuova migrazione
  `backend/migrations/versions/20260901090000_ai_media_pipeline.py`, head
  unica dopo `20260830090000`. Gli enum PostgreSQL usano
  `create_type=False` per evitare il precedente `DuplicateObjectError`.
- Nuova tabella `summary_generation_jobs` con stato
  `pending/processing/completed/failed`, utente richiedente, modello,
  prompt, input hash, versione risultante, cache hit, errore sicuro e
  timestamp.
- `summary_versions` ora salva provider, modello, prompt version, input
  hash, token input/output/cache, job e cache metadata. Vincolo univoco su
  record/hash/modello/prompt per evitare versioni duplicate concorrenti.
- `media` ora distingue chiavi original/display/thumbnail e salva
  dimensione, risoluzione, durata, stato/errori di processing, segnali
  safety e stato/note/autore/timestamp della revisione.
- `sources` contiene configurazione watermark: enabled, riferimento
  autorizzativo e regioni normalizzate.
- `backend/uv.lock` è stato generato con le nuove dipendenze.

### Classificazione e processing media

- `app/services/media_classifier.py`: classificatore reale
  `NudeNetOnnxMediaClassifier`, modello lazy e versionato
  `nudenet-3.4.2-320n`; segnali `explicitContent`, `explicitScore`,
  `faceVisible`, `faceScore`, `watermarkPresent` e
  `possibleMinorReview`. Il vecchio nome `RuleBasedMediaClassifier` resta
  solo come alias retrocompatibile verso l'implementazione reale.
- `app/services/media_processing.py`: validazione Pillow/ffprobe,
  inpainting OpenCV, transcodifica FFmpeg H.264/AAC CRF 23, yuv420p,
  faststart e massimo 1280x720; thumbnail JPEG max 640 e cinque frame al
  10/30/50/70/90%. Comandi con `shell=False`, timeout e directory
  temporanee isolate.
- `app/workers/tasks_media.py`: task idempotente/ritentabile che scarica
  l'originale da MinIO, genera varianti, classifica e aggiorna
  atomicamente media/history/audit. Gli originali non vengono mai
  sovrascritti.
- `GenericScraper` ora scarica media con streaming limitato, redirect
  manuali rivalidati, blocco SSRF per schemi non HTTP(S) e indirizzi
  privati/reserved, Content-Length, risposta troncata e limite dinamico
  immagine/video. Magic bytes e decoder reali decidono l'accettazione.
- `tasks_scraper.py` accoda il processing media soltanto dopo il commit.

### Riepiloghi OpenAI

- `app/services/summary_generator.py`: rimosso il generatore template;
  adapter OpenAI Responses con output Pydantic strutturato, `store=false`,
  timeout, prompt cache key e usage token. Nessun modello alternativo.
- `app/workers/tasks_ai.py`: job persistente asincrono, input minimizzato,
  hash deterministico, cache hit senza nuova chiamata/versione, retry con
  backoff soltanto per timeout/connessione/429/5xx e stato failed sicuro
  per errori permanenti.
- Redis applica limite richieste giornaliero per utente, richieste/minuto
  provider e budget token globale. La stima viene prenotata prima della
  chiamata, riconciliata con l'uso effettivo e rilasciata se la chiamata
  fallisce.
- `POST /records/{id}/ai-summary/regenerate` risponde 202 con il job;
  `GET /records/{id}/ai-summary/jobs/{jobId}` espone lo stato. Lettura
  ultima versione e storico restano compatibili.

### API, RBAC, storage e manutenzione

- `POST /media/{id}/review`: Admin/Operator può applicare override
  esplicito con note, autore, history e audit.
- `POST /media/{id}/reprocess`: riaccoda media falliti/pregressi.
- Contratti `MediaRead`/`RecordMedia` estesi con classificazione,
  confidenza, segnali, review/processing state e URL original/display/
  thumbnail.
- Gli URL `/media-objects/...` sono stati sostituiti da presigned URL
  MinIO brevi, costruiti con `MINIO_PUBLIC_ENDPOINT`.
- Task Beat giornaliero configura lifecycle per oggetti `tmp/` e multipart
  incompleti dopo un giorno; task notturno elimina solo oggetti media più
  vecchi della grace period e non referenziati da nessuna colonna DB.

## Frontend implementato

- La tab AI Summary avvia il job asincrono, effettua polling ogni due
  secondi e mostra processing/errore/completamento, invalidando riepilogo
  e storico al termine.
- La tab Media mostra processing, classificazione e badge "Needs review";
  Admin/Operator possono marcare safe/explicit con note e riaccodare media
  falliti. Media non classificati o in review restano trattati come
  sensibili.
- Il form Sources espone configurazione watermark Admin-only con
  autorizzazione e regione normalizzata; backend e frontend condividono
  lo stesso contratto camelCase.

## Test e verifiche eseguite

- `ruff check .`: pulito.
- Suite backend completa: **115 passed, 5 skipped**. Gli skip sono test
  opt-in già previsti; 19 warning provengono da lxml/curl_cffi su Windows.
- Test nuovi coprono soglie e aggregazione NudeNet, versione modello,
  immagine innocua con inferenza reale, watermark/originale immutabile,
  MIME e file corrotti, FFmpeg reale su MP4 sintetico, cinque frame,
  risoluzione/thumbnail, Structured Output simulato, token usage,
  minimizzazione URL/telefono, hash deterministico, AI disabilitata e
  schema del dataset redatto.
- `npm run lint`: 0 errori, due warning Fast Refresh preesistenti in
  `AuthContext.tsx` e `ThemeContext.tsx`.
- `npm run build`: completata; Vite segnala soltanto un warning relativo a
  un `tsconfig.base.json` esterno non presente, senza bloccare TypeScript o
  bundle.
- Alembic: `20260901090000 (head)`; import completo FastAPI riuscito.
- Build Docker backend reale completata nell'immagine locale
  `lavoro-esterno-backend:points-5-6` con FFmpeg 7.1.5, OpenCV,
  ONNX Runtime, NudeNet e OpenAI SDK.
- Smoke test nell'immagine: FastAPI caricato e task Celery media/AI
  registrati; `ffmpeg -version` riuscito.
- Il PostgreSQL temporaneo avviato per una migrazione live è stato
  arrestato e rimosso. L'esecuzione di `alembic upgrade head` contro quel
  container non è avvenuta perché l'autorizzazione specifica è stata
  rifiutata dall'utente/ambiente.
- Nessuna chiamata OpenAI live: mancano intenzionalmente API key e budget
  espliciti. Il comportamento fail-closed è stato verificato con test.
- Playwright end-to-end dei nuovi flussi non è stato eseguito perché lo
  stack completo con DB/account 2FA non è stato avviato in questa sessione.

## Documentazione aggiornata

- `PROGETTO.md`: punti 5 e 6 descritti nel dettaglio e spuntati, con note
  trasparenti sui limiti della verifica live.
- `README.md`, `docs/API.md`, `docs/ARCHITETTURA.md`,
  `docs/DATABASE.md`, `docs/SICUREZZA.md`, `docs/SVILUPPO.md` aggiornati.
- `docs/SICUREZZA.md` documenta minimizzazione, `store=false`, retention
  standard dei log OpenAI fino a 30 giorni e il fatto che ZDR richiede
  idoneità/approvazione separata.

## Stato e prossimi passi consigliati

Il codice dei punti 5 e 6 è implementato. Prima di un deploy effettuare:

1. Avviare uno stack Docker con `.env` di sviluppo valido e applicare
   `docker compose exec api alembic upgrade head`, verificando tabelle,
   enum e worker reali su PostgreSQL/Redis/MinIO.
2. Eseguire Playwright sui nuovi flussi AI/media con un account Admin 2FA
   e fixture sintetiche.
3. Eseguire il test OpenAI live solo con chiave dedicata e budget
   positivi minimi; verificare job, usage, cache hit e output redatto.
4. Verificare lifecycle MinIO e orphan cleanup su oggetti sintetici,
   confermando che gli originali referenziati non vengano eliminati.
5. La generazione export reale, la retention e i flussi GDPR sono stati
   completati nella sessione 6 riportata più avanti in questo documento.

## File chiave da leggere per ripartire (sessione 5)

- `backend/migrations/versions/20260901090000_ai_media_pipeline.py`
- `backend/app/services/media_classifier.py`
- `backend/app/services/media_processing.py`
- `backend/app/services/summary_generator.py`
- `backend/app/workers/tasks_media.py`
- `backend/app/workers/tasks_ai.py`
- `backend/app/workers/tasks_maintenance.py`
- `backend/app/api/v1/media.py`, `records.py`, `sources.py`
- `frontend/src/routes/records/RecordAiSummaryTab.tsx`
- `frontend/src/routes/records/RecordMediaTab.tsx`
- `frontend/src/routes/SourcesPage.tsx`
- `backend/tests/test_media_classifier.py`
- `backend/tests/test_media_processing.py`
- `backend/tests/test_summary_ai.py`
- `PROGETTO.md` § 5-6 e documentazione in `docs/`.

---

# Sessione 6 — 2 settembre 2026: Export e Sicurezza/GDPR

## Risultato

Completata la sezione 7 e i punti 2–5 della sezione 8 di `PROGETTO.md`:

- export ZIP asincroni su coda/worker `exports`, scope obbligatorio,
  manifest versionato, JSON/CSV e sole varianti media visualizzabili;
- relazione `export_job_records`, limiti 1.000 record/2 GiB, storage MinIO,
  presigned download auditato, ownership Operator e cleanup DB/object;
- retention configurabile per annunci/media/log/audit, con ricalcolo del
  canonico e invalidazione delle copie export;
- workflow Admin di cancellazione con anteprima/conferma, job persistente e
  registro HMAC di soppressione controllato dall'ingestione;
- telefono completo sempre per Admin e tramite grant individuale per gli
  altri ruoli, masking predefinito, `Cache-Control: no-store` e audit;
- security workflow con Bandit, pip-audit, npm audit, dependency review,
  Trivy e ZAP; report interno in `docs/SECURITY_REVIEW_2026-09-02.md`.

## Migrazione e file chiave

- Head Alembic: `20260902090000_exports_privacy.py`.
- Nuovi modelli: `privacy.py`; estesi `users.py` ed `export_jobs.py`.
- Nuovi worker: `tasks_exports.py`, `tasks_privacy.py`; retention riscritta
  in `tasks_maintenance.py`.
- Nuova API: `/privacy/erasure-requests`; export e admin estesi.
- UI: scope/monitoraggio Export, selezione dalla ricerca, grant telefono e
  tab Admin Privacy/Erasure.

## Verifiche eseguite

- `ruff check`: superato.
- `pytest`: 121 passed, 5 skipped opzionali.
- frontend lint: nessun errore (2 warning Fast Refresh preesistenti).
- frontend build Vite 8.2.2: superata.
- Bandit: nessun Medium/High.
- pip-audit e npm audit: zero vulnerabilità note dopo remediation.
- migrazione applicata realmente su PostgreSQL 17 temporaneo fino a head.
- build Docker backend/frontend completate; entrambe le immagini usano utenti
  non privilegiati (`app` e UID 101).
- Trivy config scan finale senza High/Critical dopo la remediation dei
  container root.
- `docker compose config --quiet` superato con `.env.example`; la copia `.env`
  temporanea usata per il controllo è stata rimossa.

## Gate ancora esterni

- Gli scan completi Trivy immagini e ZAP sono configurati in CI; i report del
  runner devono essere archiviati prima del go-live.
- Playwright richiede lo stack persistente e l'account Admin 2FA delle fixture:
  non è stato rieseguito localmente in questa sessione.
- Restano obbligatori pentest indipendente autenticato, TLS/HSTS/CSP con i
  domini definitivi, secret manager e prova di restore staging.
- I punti 1 (validazione legale fonti) e 6 (DPA/conformità provider LLM)
  della sezione 8 restano deliberatamente aperti.

---

# Sessione 7 — Stato definitivo e avvio locale su Windows

## Stato consolidato

- La sezione 7 di `PROGETTO.md` è completata: gli export sono job asincroni,
  usano una relazione DB per congelare lo scope e vengono elaborati dal worker
  Celery dedicato `worker-exports` sulla coda `exports`.
- Gli ZIP sono salvati sotto `exports/` in MinIO, hanno manifest versionato,
  JSON/CSV, hash SHA-256 e includono solo varianti display/thumbnail; gli
  originali immutabili non vengono esportati.
- I punti 2–5 della sezione 8 sono completati per la parte interna: retention
  configurabile, cancellazione GDPR asincrona con registro HMAC di
  soppressione, permesso individuale per il telefono in chiaro e security
  review automatizzata/manuale.
- Il gate di produzione resta separato: pentest esterno, TLS/secret manager,
  restore verificato e report completi Trivy/ZAP devono essere chiusi prima
  del go-live.
- L'head Alembic corrente è `20260902090000` (`exports_privacy`) e deve essere
  applicato prima di usare le nuove API.

## Avvio rapido con Docker Compose (PowerShell)

Prerequisiti: Docker Desktop avviato con Docker Compose v2. Eseguire i comandi
dalla directory radice `lavoro-esterno-1`.

### 1. Preparare l'ambiente

```powershell
Copy-Item .env.example .env
```

Generare segreti distinti. Eseguire due volte il comando da 32 byte per
`PHONE_ENCRYPTION_KEY` e `PHONE_HMAC_SECRET`, senza riutilizzare lo stesso
valore:

```powershell
[Convert]::ToBase64String(
  [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
)
```

Generare separatamente il segreto JWT da 64 byte:

```powershell
[Convert]::ToBase64String(
  [Security.Cryptography.RandomNumberGenerator]::GetBytes(64)
)
```

Aprire `.env` e sostituire almeno tutti i valori `change-me-*`. In particolare:

- assegnare i tre valori appena generati a `PHONE_ENCRYPTION_KEY`,
  `PHONE_HMAC_SECRET` e `JWT_SECRET_KEY`;
- dopo aver modificato `POSTGRES_PASSWORD`, riportare la stessa password in
  `DATABASE_URL` e `DATABASE_URL_SYNC`;
- mantenere `MINIO_ACCESS_KEY` coerente con `MINIO_ROOT_USER` e
  `MINIO_SECRET_KEY` coerente con `MINIO_ROOT_PASSWORD`;
- impostare una password dedicata in `GF_SECURITY_ADMIN_PASSWORD`.

Non committare `.env`. Generare anche `AI_CREDENTIAL_ENCRYPTION_KEY` con 32
byte casuali in base64 prima di inserire API key dalla pagina Impostazioni.
Il riepilogo predefinito usa Ollama locale e non richiede una API key. I
provider cloud richiedono credenziale, test riuscito e budget token positivo.

### 2. Costruire e avviare lo stack

```powershell
docker compose up -d --build
docker compose ps
```

Attendere che PostgreSQL, Redis, MinIO e Ollama risultino healthy. Al primo
avvio `ollama-init` scarica circa 7,2 GB per `gemma4:e2b`; `worker-ai` resta in
attesa senza bloccare frontend/API. Gli altri servizi possono richiedere
qualche secondo aggiuntivo al primo avvio.

### 3. Applicare le migrazioni

Le migrazioni non vengono applicate automaticamente all'avvio dell'API:

```powershell
docker compose exec api alembic upgrade head
docker compose exec api alembic current
```

Il secondo comando deve riportare `20260902090000 (head)`.

### 4. Creare il primo Admin

La creazione iniziale avviene fuori dall'API perché la gestione utenti richiede
già un Admin autenticato con 2FA:

```powershell
docker compose exec api python -m app.scripts.create_admin `
  --email admin@lavoro.internal `
  --password "UnaPasswordForte123!"
```

Sostituire la password di esempio con una password univoca. Aprire poi
`http://localhost`, accedere con l'account appena creato e completare il setup
2FA guidato dalla UI. Salvare immediatamente i backup code: vengono mostrati
una sola volta.

### 5. Indirizzi locali

- Applicazione: `http://localhost`
- Swagger/OpenAPI: `http://localhost/docs`
- Console MinIO: `http://localhost:9001`
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`

### 6. Diagnostica

```powershell
docker compose ps
docker compose logs -f api
docker compose logs -f worker-exports
docker compose logs -f worker-media
docker compose logs -f worker-ai
```

Ogni comando `logs -f` rimane in ascolto; interromperlo con `Ctrl+C` prima di
passare al successivo. Per esaminare anche scraping, retention e scheduler usare
rispettivamente `worker-scraper` e `scheduler`.

### 7. Arresto sicuro

```powershell
docker compose down
```

Questo arresta i container conservando i volumi PostgreSQL, MinIO e gli altri
dati locali. La variante `docker compose down -v` elimina i volumi e quindi i
dati: è un'operazione distruttiva, da usare solo quando la cancellazione
completa dell'ambiente è esplicitamente voluta e dopo aver verificato eventuali
backup.

## Troubleshooting Docker Desktop/Windows

### `localhost` restituisce HTTP 500 o resta in attesa

È disponibile `scripts/windows/Repair-Localhost.ps1`. Senza parametri esegue
soltanto la diagnosi; `-Repair`, da PowerShell elevata, termina un listener
stale esclusivamente quando IPv4 risponde `200`, IPv6 non risponde e PID, nome
e percorso identificano esattamente `C:\Program Files\WSL\wslrelay.exe`.
Il frontend Docker usa inoltre `VITE_API_URL=/api/v1`, quindi il fallback
`http://127.0.0.1` mantiene operative anche autenticazione e chiamate API.

Verifica del 7 settembre 2026: lo script ha identificato IPv4 `200`, IPv6 in
timeout e `wslrelay.exe` PID 62736 nel percorso ufficiale. L'ambiente Codex
non può ottenere autonomamente il token UAC di Windows; la modalità `-Repair`
va quindi eseguita una volta da una PowerShell aperta come amministratore.
Nel frattempo il frontend ricostruito è pienamente operativo su
`http://127.0.0.1`, incluso `POST /api/v1/auth/login`.

Su Docker Desktop con backend WSL, `localhost` può risolvere prima a `::1` e
venire intercettato da `wslrelay` senza raggiungere nginx. Le porte nginx sono
perciò pubblicate esplicitamente su `127.0.0.1`; il browser deve quindi poter
ripiegare immediatamente su IPv4. Per distinguere un problema del relay da un
errore applicativo usare:

```powershell
curl.exe --noproxy "*" -4 -I http://localhost/
curl.exe --noproxy "*" -4 http://localhost/api/v1/healthz
```

Entrambe le richieste devono raggiungere nginx; la prima restituisce `200`.
Come alternativa diagnostica temporanea aprire direttamente
`http://127.0.0.1`. Dopo una modifica alle porte ricreare soltanto nginx:

```powershell
docker compose up -d --force-recreate nginx
```

Se `::1:80` continua a risultare in ascolto dopo la ricreazione, verificare il
processo con `Get-NetTCPConnection -State Listen -LocalPort 80`: può trattarsi
di un `wslrelay` rimasto in memoria con il vecchio mapping. In questa sessione
anche il riavvio di Docker Desktop non lo ha rimosso; il relay è stato
terminato solo dopo averne controllato PID e tutte le porte inoltrate. Questa
operazione può interrompere temporaneamente altri servizi WSL e non va eseguita
alla cieca. Dopo la rimozione del relay stale, `localhost` è tornato a
ripiegare su `127.0.0.1` e ha risposto HTTP 200.

### I container backup falliscono su `set -eu`

Gli script montati nei container Alpine devono avere terminatori LF. Il file
`.gitattributes` impone `eol=lf` a tutti i file `.sh`. Il sintomo tipico di un
checkout CRLF è `set: illegal option -` oppure `set: -\r: invalid option`.
Dopo un riavvio del motore Docker, se PostgreSQL o MinIO non sono ancora
raggiungibili, i backup ritentano dopo 60 secondi; un dump PostgreSQL viene
pubblicato soltanto quando `pg_dump` e la compressione sono entrambi riusciti.
Dopo aver normalizzato un checkout, ricreare solo i servizi backup:

```powershell
docker compose up -d --force-recreate backup-postgres backup-minio
docker compose ps backup-postgres backup-minio
docker compose logs --tail=50 backup-postgres backup-minio
```

Questi comandi non eliminano né ricreano i volumi dati.

### La tab Media restituisce HTTP 500

Se il traceback contiene `HTTPConnectionPool(host='localhost', port=9000)`
durante `presigned_get_object`, il client MinIO sta tentando di determinare la
regione interrogando l'endpoint pubblico dall'interno del container API. In
Docker, `localhost` indica il container stesso. La configurazione corretta
mantiene separati gli endpoint e specifica la regione:

```dotenv
MINIO_ENDPOINT=minio:9000
MINIO_PUBLIC_ENDPOINT=localhost:9000
MINIO_REGION=us-east-1
```

`docker-compose.yml` passa lo stesso valore a MinIO come
`MINIO_SITE_REGION`. Il backend usa la regione esplicita per generare URL
presigned senza richieste di rete verso `MINIO_PUBLIC_ENDPOINT`. Dopo una
modifica ricreare soltanto MinIO e API, preservando il volume dati:

```powershell
docker compose up -d --force-recreate minio
docker compose up -d --build api
```

Non usare `docker compose down -v`: eliminerebbe anche i media salvati.

### Verifica della correzione del 2 settembre 2026

- `backup-minio.sh`, `backup-postgres.sh` e `restore-postgres.sh`: zero byte
  CR/CRLF;
- backup PostgreSQL: dump valido completato e rotazione eseguita;
- backup MinIO: bucket applicativo creato vuoto e mirror completato;
- `backup-postgres`, `backup-minio` e `nginx`: stato `Up` stabile;
- `http://localhost/` e `GET /api/v1/healthz`: HTTP 200;
- nessun volume Docker è stato eliminato o ricreato.

# Sessione 8 — 3 settembre 2026: AI multiprovider

- Migrazione `20260903090000` con `ai_settings`, `ai_provider_configs` e
  snapshot provider/revisione nei job. Le versioni precedenti restano
  consultabili; la cache distingue anche il provider.
- Default `ollama` + `gemma4:e2b`, limite 20 richieste/giorno per utente e 10
  richieste/minuto. Il budget cloud parte da zero e non blocca il provider
  locale.
- Provider disponibili: Ollama, OpenAI, Anthropic/Claude, Google Gemini,
  Groq, Mistral, OpenRouter e custom OpenAI-compatible. Nessun fallback
  silenzioso; output sempre validato contro lo schema del riepilogo.
- Nuova pagina Admin `/settings/ai` con catalogo modelli live, ID manuale,
  test connessione, attivazione, limiti e credenziali write-only cifrate.
- Nuovi servizi `ollama` e `ollama-init`, volume `ollama-data`; la porta non è
  pubblica e il worker AI usa concorrenza 1.

Per configurare provider cloud, generare la chiave dedicata:

```powershell
[Convert]::ToBase64String(
  [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
)
```

Usare il risultato come `AI_CREDENTIAL_ENCRYPTION_KEY`, ricreare `api` e
`worker-ai`, quindi inserire la chiave del provider da `/settings/ai`. Per
gli ambienti reali conservarne una copia nel secret manager/backup protetto:
senza questa chiave le credenziali provider cifrate non sono recuperabili. Per
diagnosticare Ollama:

```powershell
docker compose ps ollama ollama-init worker-ai
docker compose logs -f ollama-init
docker compose exec ollama ollama list
```

Il primo download è voluminoso ma non viene ripetuto se il modello è già
presente nel volume. Non usare `docker compose down -v`, che cancellerebbe
anche `ollama-data` oltre ai dati applicativi.

Verifica conclusiva del 3 settembre 2026:

- migrazione applicata: `20260903090000 (head)`;
- Ollama healthy, `gemma4:e2b` presente (7,2 GB), secondo avvio di
  `ollama-init` concluso con `model already present`;
- generazione sintetica reale conforme a `SummaryPayload`, con token usage
  restituito da Ollama;
- `worker-ai` operativo sulla sola coda `ai` con concorrenza 1;
- backend: Ruff verde e `150 passed` (inclusi i test Chromium prima saltati);
- frontend: lint senza errori, build completata e Playwright AI settings
  `1 passed`;
- homepage e `/api/v1/healthz`: HTTP 200; endpoint impostazioni senza sessione:
  HTTP 401 come previsto.

Nel `.env` locale `AI_CREDENTIAL_ENCRYPTION_KEY` resta volutamente senza un
valore generato dal repository: Ollama funziona comunque, mentre prima di
salvare credenziali cloud l'operatore deve impostare una chiave casuale come
descritto sopra e ricreare `api` e `worker-ai`.

# Sessione 9 — 4 settembre 2026: Record, Admin e console operative

Completati i dieci rilievi funzionali:

- `/records` è ora elenco, ricerca, filtri ed export; `/search` reindirizza
  conservando la query string. “All Sources” esegue una normale query non
  filtrata. Il `204` dell'AI Summary viene normalizzato a `null`.
- Gli utenti sospesi possono essere riattivati da Admin con 2FA. Sospensione e
  riattivazione aggiornano il security stamp; auto-sospensione e sospensione
  dell'ultimo Admin attivo sono bloccate.
- `/account` è raggiungibile dall'header e gestisce password, setup 2FA e
  rigenerazione dei backup code. Profile e Search sono rimossi dalla sidebar;
  Support è rimosso dall'header.
- Source Priorities usa job persistenti sulla coda `maintenance` per
  ricalcolare i canonici. La policy è priorità, completezza, recenza e ID,
  senza eccezione Bakeca.
- Classifiers espone modello/versione NudeNet, soglie revisionate, statistiche
  e reprocess bulk dei falliti o da revisionare, preservando gli override.
- Notifications usa eventi persistenti deduplicati e ricevute per utente, con
  visibilità RBAC e retention a 90 giorni. System Status controlla API,
  PostgreSQL, Redis, MinIO, Ollama e le quattro code Celery senza esporre
  dettagli interni.

Migrazione: `20260904090000_operations_console.py`, applicata su PostgreSQL
reale e verificata come `head`. Aggiunge `media_classifier_settings`,
`source_priority_recalculation_jobs`, `notification_events` e
`notification_reads`.

Verifica finale:

- backend: Ruff verde e suite completa `154 passed`, inclusi i test di
  regressione per route notifiche e canonici;
- frontend: lint senza errori (restano due warning Fast Refresh preesistenti),
  build Vite completata;
- Playwright mirato: `3 passed` per Records non filtrati, AI Summary senza
  versione e pagina Account;
- Docker: build API/frontend/worker riuscite, migrazione all'head, Ollama
  healthy e worker `scraping`, `maintenance`, `media`, `ai`, `exports` online;
- il Dockerfile backend installa ora le dipendenze dal `uv.lock` in un layer
  separato, evitando sia il segfault di pip sia reinstallazioni a ogni modifica
  del codice.

Per diagnosticare queste funzioni:

```powershell
docker compose exec api alembic current
docker compose exec api celery -A app.workers.celery_app:celery_app inspect active_queues
docker compose logs -f api worker-scraper worker-media worker-ai worker-exports
```

Non usare `docker compose down -v`: tutti i volumi applicativi esistenti sono
stati preservati durante l'aggiornamento.

# Sessione 10 — 4 settembre 2026: testo completo attraverso `<br>`

Il motore generico non usa più `selector::text` per i campi testuali: quella
forma restituiva nodi separati e un campo non multiplo conservava soltanto il
primo segmento prima di `<br>`. Ora seleziona ogni elemento, percorre tutti i
nodi testuali in ordine, ignora `script`/`style` e converte i `<br>` in `\n`.
I tag inline restano testo continuo e `<br><br>` conserva una riga vuota.

La vista Overview usa `whitespace-pre-line`, quindi la struttura estratta è
visibile. Non è richiesto alcun aggiornamento dello schema: gli annunci già
salvati verranno corretti al successivo scan esplicitamente avviato per la
fonte; il deployment non avvia scraping automatici.

Verifica: Ruff verde, suite backend `156 passed`, lint frontend senza errori,
build Vite completata e test sintetico eseguito anche dentro l'immagine API.
Il normale endpoint “Test configuration” sulla fonte configurata ha trovato 25
annunci; la descrizione campione è stata estratta in 735 caratteri su 3 righe,
senza warning. API, frontend e `worker-scraper` sono stati ricostruiti e sono
operativi; nessuno scan con persistenza è stato avviato.

Durante il test è comparso un warning perché il `JWT_SECRET_KEY` dell'ambiente
locale corrente è lungo 20 byte. Non è stato ruotato automaticamente, perché
la rotazione invalida le sessioni: prima di un uso reale sostituirlo con il
valore casuale da 64 byte già indicato nel runbook Windows.

# Sessione 11 — 4 settembre 2026: observability completa

Completata e collaudata dal vivo l'intera sezione 9. L'API espone ora
`GET /metrics` solo sulla rete Docker, fuori da `/api/v1`, senza autenticazione
e senza comparire nell'OpenAPI. `prometheus-fastapi-instrumentator` raccoglie
richieste, status, latenza per route normalizzata e richieste attive; un
collector DB-backed pubblica, per UUID e slug della fonte, run 24h/7d, nuovi
annunci, ultimo stato/successo, fallimenti consecutivi e durata dei run attivi.
Un errore PostgreSQL lascia disponibili le metriche HTTP e porta la gauge del
collector a zero.

Lo stack include Prometheus 3.14, Grafana 13.2, Loki 3.7, Alloy 1.19,
postgres_exporter 0.20.1, redis_exporter 1.90.0, node_exporter 1.12.1 e Celery
Exporter 0.12.2. Quest'ultimo è costruito dal commit `d45a395e`, verificato con
SHA-256, perché include anche l'istogramma del tempo di attesa in coda. Celery
emette gli eventi completi e tutte le code `scraping`, `maintenance`, `media`,
`ai`, `exports` sono monitorate. Alloy legge il socket Docker in sola lettura,
filtra il progetto Compose, esclude se stesso e invia a Loki log etichettati
con `compose_project`, `service`, `container` e `stream`; retention 90 giorni.

Grafana provisiona nel folder **Lavoro Esterno** le dashboard **API Health**,
**Celery Workers** e **Scraping Sources**, più sette regole senza contact point:
API down, target observability down, coda lunga, coda senza avanzamento,
fallimenti scraping consecutivi, collector scraping down e spazio libero dei
volumi PostgreSQL/MinIO sotto il 15%. Tutte dichiarano esplicitamente gli stati
NoData ed errore di valutazione.

Collaudo finale:

- backend: Ruff verde e suite completa `160 passed`; lock `uv` aggiornato;
- `docker compose config`, Prometheus config/rules, Alloy format/config,
  provisioning YAML e JSON dashboard validi;
- tutti gli otto target Prometheus `UP`, cinque recording rule `ok`,
  `pg_up=1`, `redis_up=1`, collector scraping `=1` e metriche spazio presenti
  per entrambi i mount;
- task Celery controllato osservato come sent/received/started/succeeded, con
  runtime e queue wait; log API e worker interrogabili in Loki;
- tre dashboard e sette alert caricati automaticamente, regole tutte healthy;
- prova reale dell'alert API: `inactive → pending → firing → inactive` dopo il
  ripristino; API nuovamente `UP`;
- tutti i servizi Compose operativi (il container one-shot `ollama-init` è
  terminato correttamente con exit code 0). Nessun volume è stato eliminato o
ricreato durante il collaudo.

# Sessione 12 — 7 settembre 2026: duplicazione e riabilitazione Sources

La gestione Sources espone ora esplicitamente `enabled` nelle risposte lista e
dettaglio, separando lo stato operativo dalla salute del connettore. Sono stati
aggiunti `POST /api/v1/sources/{source_id}/duplicate` (solo Admin) e
`POST /api/v1/sources/{source_id}/enable` (Admin/Operator). La duplicazione
assegna nuova identità e timestamp, copia in modo atomico URL base, priorità,
configurazione completa dello scraper e impostazioni watermark, ma non annunci,
run o errori. La copia nasce `offline` e disabilitata; collisioni sullo slug,
anche concorrenti, restituiscono 409. Entrambe le operazioni sono auditate senza
registrare configurazioni o riferimenti sensibili; Enable è idempotente.

La tabella mostra agli Admin l'azione Duplicate, con nome e slug suggeriti e
suffisso numerico anti-collisione. Le fonti ferme mostrano Enable ad Admin e
Operator e non espongono Scan, Pause o Disable finché non vengono riattivate.
La UI invalida lista e riepilogo dopo ogni operazione e mantiene visibili gli
errori nella modale o nella pagina.

Verifica conclusiva:

- Ruff verde e suite backend completa `176 passed`;
- lint frontend senza errori (restano i due warning Fast Refresh preesistenti)
  e build Vite completata;
- Playwright mirato `5 passed`, eseguito anche contro il frontend del Compose;
- prova API reale su PostgreSQL: route e contratto OpenAPI presenti, Duplicate
  201 con configurazione identica e stato disabilitato, Enable 204 con stato
  healthy; le due fonti temporanee sono state eliminate (`temporary_sources=0`);
- health HTTP 200 e tutti gli 8 target Prometheus UP;
- i volumi PostgreSQL e MinIO conservano la data di creazione del 4 settembre
  2026: nessun volume è stato eliminato o ricreato.

Resta il warning già noto per il `JWT_SECRET_KEY` locale di 20 byte: non è stato
ruotato automaticamente perché la rotazione invaliderebbe le sessioni attive.

# Sessione 13 — 7 settembre 2026: campi custom dello scraper

La pipeline non scarta più i campi configurati al di fuori dello schema core.
La migrazione `20260907120000_advertisement_custom_fields.py` aggiunge lo
snapshot JSONB `advertisements.custom_fields`; `GenericScraper.normalize()` vi
conserva stringhe, liste e valori mancanti e l'upsert lo sostituisce a ogni
scan. Telefono e media restano nei rispettivi flussi e non vengono duplicati.
L'hash del contenuto comprende ora il JSON custom con ordinamento stabile e i
valori non vuoti contribuiscono alla completezza nella scelta canonica.

Le API Overview e Occurrences espongono `customFields`. L'Overview mostra i
campi dell'annuncio canonico, usando i badge esistenti per `tags`; ogni riga
Occurrences ha un dettaglio espandibile con lo snapshot della singola fonte.
I nuovi export dichiarano `export-v2` e includono `custom_fields` sia nel JSON
sia in una colonna CSV serializzata deterministicamente. Gli export già creati
non vengono modificati e i dati custom scartati prima di questa migrazione
saranno disponibili soltanto dopo un nuovo scan esplicitamente avviato.

Prima del riavvio applicare:

```powershell
docker compose exec api alembic upgrade head
```

I campi custom non entrano nella ricerca dinamica e non vengono inviati ai
provider AI. La configurazione di prova continua a mostrarli immediatamente,
mentre la persistenza avviene soltanto durante uno scan reale.

Verifica conclusiva: migrazione applicata a `head`, Ruff verde sui file
modificati, suite backend completa `181 passed`, lint frontend senza errori
(due warning Fast Refresh preesistenti), build Vite completata e Playwright
custom-fields `1 passed` tramite `http://127.0.0.1`. Lo scan reale della fonte
`prova` è terminato `completed` con 25 annunci e zero errori: tutti e 25 hanno
`tags` JSON array in `custom_fields`, nessuno contiene chiavi core duplicate e
24 sono già annunci canonici dei rispettivi record (il restante condivide un
record il cui canonico è un'altra occorrenza). API, frontend, worker scraper ed
export sono operativi. `localhost` conserva il problema esterno del relay IPv6
Windows già documentato; l'endpoint IPv4 ha risposto HTTP 200 durante i test.

# Sessione 14 — 8 settembre 2026: aggregazione universale dei campi custom

La persistenza era già generica: la verifica sul database ha confermato che la
chiave arbitraria `prova` era salvata in 25 annunci. Il dato risultava però
invisibile nell'Overview quando apparteneva a un'occorrenza diversa da quella
canonica, perché `GET /records/{id}` leggeva solo
`canonical_ad.custom_fields`.

L'endpoint Overview espone ora `customFieldGroups`, una vista calcolata su tutte
le occorrenze del record. Ogni valore conserva fonte, codice fonte, annuncio e
flag canonico. Valori discordanti non vengono sovrascritti; vengono rimossi
soltanto duplicati JSON identici della stessa fonte. I nomi restano
case-sensitive ed esattamente come configurati, mentre campi vuoti non sono
mostrati. `customFields` continua a rappresentare lo snapshot canonico per
compatibilità con client precedenti.

La UI mostra la sezione "All collected fields" con provenienza e aggrega i
badge `tags` da tutte le fonti. Occurrences ed export continuano a usare lo
snapshot per-annuncio. Non è richiesta una migrazione aggiuntiva e i valori già
presenti diventano visibili appena API e frontend vengono ricostruiti; solo i
dati scartati prima della migrazione del 7 settembre richiedono un nuovo scan.

Verifica conclusiva: test custom-fields `7 passed`, suite backend completa
`183 passed`, Ruff verde sui file interessati, lint frontend senza errori (due
warning Fast Refresh preesistenti), build Vite completata e Playwright mirato
`1 passed`. API e frontend sono stati ricostruiti senza modificare i volumi;
pagina e health API rispondono `200`. Una richiesta autenticata reale ha
restituito per un record già esistente i gruppi `prova` e `tags`, confermando
che non serve ripetere lo scraping per i valori già persistiti.

# Sessione 15 — 8 settembre 2026: paginazione href e JavaScript

La fonte `prova` aveva `max_pages=1`; inoltre `a.page-link` trovava sia la
pagina corrente sia “Seguente” e nessuno dei controlli esponeva `href`. Il
motore precedente cercava esclusivamente il primo `href` e interrompeva la
discovery senza diagnostica.

La discovery ora richiede un controllo Next univoco, usa automaticamente
`href` quando presente e, nei mode `dynamic`/`stealth`, usa una `page_action`
Scrapling con click DOM quando il controllo è JavaScript-only. Attende una
variazione dell'URL o degli annunci, deduplica i link e blocca cicli e cambi di
origine. La migrazione `20260908100000` aggiunge a `scrape_runs` pagine
visitate, modalità e motivo di arresto; le anomalie diventano errori sicuri
nello storico.

“Test configuration” invia la bozza del form senza salvarla e mostra la stessa
diagnostica. La fonte `prova` è stata aggiornata tramite il normale endpoint
Admin, con audit, usando
`nextPageSelector = a.page-link[aria-label="Next"]` e `maxPages = 5`.

Verifica conclusiva: migrazione applicata a `head` (`20260908100000`), test
reale della configurazione completato su 5 pagine in modalità `click`, arresto
per `max_pages`, 119 URL di annunci unici e nessun warning. La suite backend
completa è verde (`192 passed`), incluso il controllo sulla propagazione sicura
degli errori di paginazione nello storico. Ruff è verde, lint frontend non
segnala errori (restano due warning Fast
Refresh preesistenti), build Vite completata e Playwright Sources `6 passed`.
API, frontend, nginx e worker scraper sono stati ricostruiti preservando i
volumi. È stato inoltre accodato uno scan reale della fonte: l'elaborazione è
asincrona e può richiedere tempo perché visita e scarica i singoli annunci e i
relativi media rispettando i limiti della fonte.

# Sessione 16 — 8 settembre 2026: proxy rotator globale

Introdotti pool proxy globali riutilizzabili con endpoint HTTP/HTTPS/SOCKS,
selezione least-recently-used e policy fail-closed per le fonti assegnate.
Username/password sono cifrati AES-256-GCM con una chiave dedicata e non
compaiono in API, log o audit. Il proxy viene applicato a robots.txt, listing,
pagine annuncio e download media; gli errori di rete e HTTP 403/407/429 ruotano
su un massimo di tre endpoint con cooldown 5/15/30/60 minuti.

La migrazione `20260908130000_proxy_rotator.py` crea pool, endpoint, membership
e storico tentativi, collega le fonti e amplia la diagnostica dei run. La UI
Admin e disponibile in `/settings/proxies`; il form Source assegna il pool e
mostra esplicitamente il comportamento fail-closed. Prima di salvare
credenziali valorizzare `PROXY_CREDENTIAL_ENCRYPTION_KEY` con 32 byte casuali
in base64; per gateway interni usare l'allowlist server-side dedicata.

Sono supportati HTTP, HTTPS, SOCKS4 e SOCKS5. Poiche `httpx` non implementa
SOCKS4, quel solo percorso usa `curl_cffi`/libcurl mantenendo gli stessi limiti
di dimensione, redirect controllati e verifiche SSRF. Host e DNS sono
rivalidati al momento dell'uso per impedire DNS rebinding; un pool assegnato
non effettua mai fallback diretto.

Verifica conclusiva: migrazione applicata a `20260908130000 (head)`, suite
backend completa `201 passed` e test proxy mirati `9 passed`; Ruff verde,
lint frontend senza errori (due warning Fast
Refresh preesistenti), build Vite completata. Playwright Sources `6 passed` e
Proxy Settings `1 passed` tramite `http://127.0.0.1`. API, frontend e worker
scraper sono stati ricostruiti preservando tutti i volumi; health API e pagina
rispondono `200` su IPv4. `localhost` puo ancora essere intercettato dal relay
IPv6 stale di WSL documentato nelle sessioni precedenti.

# Sessione 17 — 9 settembre 2026: scraping automatico fixed-delay

Ogni fonte dispone ora di uno schedule opzionale configurabile dalla pagina
Sources da un Admin con 2FA, in minuti/ore/giorni tra 15 minuti e 30 giorni.
Non è una periodicità ancorata all'orologio: `next_scrape_at` viene calcolato
solo alla conclusione del run. Esempio verificato: scan 10:00–10:20 e intervallo
di un'ora producono la nuova scadenza 11:20. Anche un run manuale o fallito
riavvia il countdown; durante pending/running la scadenza resta nulla.

La migrazione `20260908160000_source_scrape_scheduling.py` aggiunge stato e
revisione alle fonti, run `pending`, origine manual/scheduled e task ID. Un
indice univoco parziale vieta più run attivi per fonte. Celery Beat esegue il
dispatcher ogni minuto con lock `SKIP LOCKED`, ripubblica pending non acquisiti
dopo due minuti e chiude i running stale oltre sei ore (con margine per il hard
time limit del worker). Lo schedule viene riletto al termine, quindi modifiche o
disattivazioni effettuate durante uno scan si applicano alla scadenza seguente.

La UI mostra stato, frequenza, ultima conclusione, prossima esecuzione e origine
dei run in `Europe/Rome`; gli Operator conservano il solo avvio manuale. Le
variabili operative sono `SCRAPE_PENDING_RETRY_MINUTES`, `SCRAPE_STALE_HOURS` e
`SCRAPE_SCHEDULER_BATCH_SIZE`. Non usare `docker compose down -v`: la migrazione
è additiva e preserva dati, media e configurazioni proxy.

Verifica eseguita: Ruff verde; suite backend `212 passed`; lint frontend
senza errori (restano due warning Fast Refresh preesistenti); build Vite
completata; Playwright Sources `7 passed`, incluso il salvataggio dello
schedule. Migrazione applicata a `20260908160000 (head)`, indice parziale
verificato su PostgreSQL, dispatcher osservato ogni minuto con esito
`published: 0` quando nessuna fonte è abilitata allo schedule, pagina e health
API entrambe `200` su `127.0.0.1`. Il test browser va eseguito con
`PLAYWRIGHT_BASE_URL=http://127.0.0.1` su questa macchina a causa del relay
IPv6 stale di `localhost` già documentato.

# Sessione 18 — 9 settembre 2026: refresh continuo e storico occorrenze

Ogni scraping manuale o scheduled confronta ora l'occorrenza identificata
dalla terna record/fonte/URL. Titolo, descrizione e tutti i campi custom hanno
un hash deterministico separato dall'hash del set ordinato e deduplicato dei
media. Se nulla cambia vengono aggiornati soltanto `last_seen_at`
dell'annuncio e dei media riconosciuti: `scraped_at`, canonico, revisioni e
storico restano invariati e nessun media viene ricaricato o riclassificato.

Una modifica materiale incrementa `Advertisement.revision` e
`Record.content_revision`, aggiorna lo snapshot corrente e crea una riga
immutabile in `advertisement_versions` con i soli nomi dei campi cambiati. I
media nuovi vengono aggiunti; quelli assenti diventano `is_current=false`
solo quando il download del set è completo. Un download parziale mantiene i
media precedenti, e gli originali MinIO non vengono mai sovrascritti. Gli
annunci non incontrati durante uno scan non vengono considerati rimossi.

La tab Occurrences mostra revisione e ultimo cambiamento; History include gli
aggiornamenti dello scraper. Il nuovo endpoint
`GET /records/{recordId}/occurrences/{advertisementId}/versions` espone gli
snapshot autorizzati. Media, Overview ed export usano solo media correnti. I
riepiloghi AI salvano la revisione del record e rispondono con `isStale=true`
quando i dati sono cambiati; la rigenerazione resta manuale per evitare costi
imprevisti.

Migrazioni applicate: `20260909100000_continuous_record_versions.py` e
`20260909103000_backfill_occurrence_hashes.py` (head), con backfill verificato
di 400 versioni iniziali per 400 annunci e zero hash mancanti. I run ora
espongono `itemsUpdated` e `itemsUnchanged`; lo schedule fixed-delay della
sessione precedente è invariato. Verifica: suite backend `215 passed`, test
mirati successivi `29 passed`; Ruff verde; lint frontend senza errori (due
warning Fast Refresh preesistenti), build Vite completata; API, frontend e
worker interessati ricostruiti senza rimuovere volumi; health IPv4 `200`.
Playwright `custom-fields.spec.ts` è verde (`1 passed`) e copre sia i campi
aggregati sia dettaglio e storico revisioni dell'occorrenza.

# Sessione 19 — 9 settembre 2026: localizzazione italiana

L’esperienza applicativa è ora in italiano. Il frontend inizializza `i18next`
e `react-i18next` con lingua e fallback `it`, imposta `lang="it"` e centralizza
la formattazione in `it-IT` con fuso `Europe/Rome`. Route, payload JSON, enum,
tabelle e identificatori tecnici restano invariati. Provider, modelli, nomi
delle fonti, contenuti acquisiti e campi personalizzati non vengono tradotti.

I nuovi riepiloghi usano `summary-v2-it`; `summary-v1` resta disponibile per
i job storici già congelati. La migrazione
`20260909110000_italian_localization.py` aggiorna in modo idempotente soltanto
la configurazione globale e incrementa la revisione. Non rigenera versioni
esistenti. Una versione prompt sconosciuta fallisce esplicitamente, senza
fallback silenzioso.

Gli errori di validazione FastAPI/Pydantic conservano `loc` e `type`, ma
restituiscono un messaggio leggibile in italiano e non riflettono l’input
potenzialmente sensibile. Il controllo frontend `npm run check:i18n` impedisce
di introdurre nuovamente le più comuni stringhe inglesi direttamente in JSX,
placeholder, `title` e `aria-label`.

Comandi di verifica:

```powershell
cd frontend
npm run check:i18n
npm run lint
npm run build

cd ..\backend
ruff check app tests
pytest
alembic upgrade head
```

Per aggiornare lo stack senza perdere dati, ricostruire `api`, `frontend` e
`worker-ai`, quindi applicare Alembic. Non usare `docker compose down -v`.

Verifica finale della sessione: Ruff superato e suite backend completa con
`216 passed`; lint frontend senza errori (restano i due avvisi Fast Refresh
preesistenti), controllo `check:i18n` e build Vite superati. I 16 test
Playwright isolati per Panoramica, Record, Riepilogo AI, Fonti, pianificazione,
proxy, Account e campi personalizzati sono verdi. La migrazione attiva è
`20260909110000 (head)`; pagina, health API, API, frontend e worker AI sono
operativi e la pagina pubblicata dichiara `<html lang="it">`.

La suite Playwright che usa l'Admin reale richiede l'allineamento delle
credenziali locali in `frontend/e2e/fixtures.ts`: sul volume corrente la
password storica della fixture non corrisponde all'utente e l'API restituisce
correttamente “Email o password non validi”. Non è stata modificata o
reimpostata automaticamente alcuna credenziale reale. Il problema non riguarda
la localizzazione; i flussi equivalenti con API simulate sono coperti dai 16
test verdi sopra indicati.

# Sessione 20 — 9 settembre 2026: commenti e documentazione allineati

È stata revisionata la base applicativa e infrastrutturale completa. I moduli
frontend che non dichiaravano ancora la propria responsabilità hanno ora un
header conciso; lo stesso vale per lo schema operativo, gli script, i test E2E
e unitari e i file infrastrutturali privi di contesto. Tutti i route handler
FastAPI ora hanno una docstring utile anche alla descrizione OpenAPI. I
commenti spiegano responsabilità, sicurezza, concorrenza e fallback non ovvi,
senza tradurre riga per riga codice già leggibile.

La documentazione è stata riallineata al comportamento corrente: API di
duplicazione/riabilitazione Sources, revoca delle sessioni, versioni delle
occorrenze, worker export e download firmato; metriche ed exporter realmente
attivi; proxy e schedule delle fonti; pHash, backup MinIO e retention effettiva
di annunci, media, run, notifiche, audit ed export. `docs/SVILUPPO.md` include
ora la convenzione da seguire per mantenere sincronizzati commenti, OpenAPI,
documenti e handoff.

Verifica finale: Ruff check e format verdi; suite backend `209 passed, 7
skipped`; lint frontend senza errori (restano due warning Fast Refresh
preesistenti); build Vite completata; `docker compose config --quiet` valido.
`npm ci` ha ripristinato le dipendenze dichiarate e `npm audit` non segnala
vulnerabilità. Non sono stati modificati dati, credenziali o volumi Docker.

# Sessione 21 — 10 settembre 2026: supporto a “Chrome reale”

L'errore mostrato dal test di configurazione con `realChrome` dipendeva
dall'assenza della distribuzione Google Chrome nell'immagine backend:
Patchright cercava correttamente `/opt/google/chrome/chrome`, mentre il
Dockerfile installava soltanto Chromium. L'immagine installa ora entrambi i
browser e verifica durante la build che l'eseguibile di Chrome sia presente;
in questo modo la build fallisce subito qualora il canale `chrome` non sia
realmente utilizzabile.

La distinzione tra Chromium predefinito e Google Chrome usato dall'opzione
“Chrome reale”, insieme al comando di ricostruzione di API e worker scraper,
è documentata in `README.md` e `docs/SVILUPPO.md`. È stato inoltre corretto un
commento non più attuale nel workflow CI relativo a `uv.lock`.

Collaudo live completato su Docker x86_64: build delle immagini `api` e
`worker-scraper` riuscita; Google Chrome `153.0.8010.36` presente; apertura di
un persistent context Patchright con `channel="chrome"` riuscita; chiamata
reale `StealthyFetcher.async_fetch(..., real_chrome=True)` verso
`https://example.com` conclusa con HTTP 200. Dopo l'avvio delle dipendenze il
worker si è collegato a Redis ed è entrato nello stato `ready`; health check
API `/api/v1/healthz` HTTP 200. Frontend e nginx sono stati ricostruiti e la
pagina pubblicata `/sources` risponde HTTP 200, pronta per la verifica manuale.

Verifiche statiche: Ruff superato, test mirati degli schema Sources `17
passed`, `docker compose config --quiet` valido e `git diff --check` senza
errori. Nessun volume Docker esistente è stato eliminato o ricreato durante
il collaudo.

# Sessione 22 — 14 settembre 2026: impaginazione interna dei campi

Lo scraper generico supporta ora la navigazione per singolo campo nelle
pagine annuncio, separata dalla paginazione degli elenchi. Una configurazione
`fields.<nome>.pagination` indica `nextSelector`, `maxPages` (default 10,
massimo 50) e `maxItems` (default 1000, massimo 5000). La funzione richiede
`dynamic` o `stealth`, segue link della stessa origine nel rispetto di
`robots.txt` oppure controlli JavaScript che aggiungono o sostituiscono il
contenuto, applicando il rate limit a ogni transizione.

Le liste semplici, i dizionari `keyValue` e le coppie `posterVideo` vengono
uniti senza duplicati e mantenendo il primo valore incontrato. Il nuovo tipo
`items` produce liste di oggetti: `containerSelector` identifica commenti o
recensioni e `itemFields` ne estrae i sotto-campi scalari. I campi standard
scalari (`phone`, `title`, `description`) non sono impaginabili; immagini e
video sì. Ogni campo usa una pagina browser isolata nella sessione condivisa,
evitando interferenze tra caroselli distinti.

Timeout, contenuto ripetuto, controllo ambiguo, cross-origin, divieto robots e
limiti conservano quanto già raccolto. Il run registra una diagnostica
`field_pagination_incomplete`; la prova configurazione restituisce inoltre
`fieldPagination` con modalità, pagine, elementi, motivo di arresto e stato
di completezza. La modale Sources configura paginazione e sotto-campi e mostra
queste informazioni. Il formato resta nel JSONB `scrape_config`: nessuna
migrazione DB e piena compatibilità con le fonti precedenti; duplicazione e
import/export conservano i nuovi valori.

Verifica finale: Ruff verde; suite backend completa `268 passed`; fixture
browser locali `18 passed` e collaudo nell'immagine backend `16 passed` senza
skip prima dell'aggiunta degli ultimi due casi di regressione; lint frontend
senza errori (i due warning Fast Refresh preesistenti); build Vite completata;
E2E Sources `7 passed` sia sul server di sviluppo sia sul bundle Docker;
OpenAPI pubblicato verificato; `docker compose config --quiet` e
`git diff --check` validi. API e pagina `/sources` rispondono HTTP 200 e il
worker scraper è connesso a Redis e `ready`.

Nessun volume esistente è stato eliminato o ricreato. Lo stack era assente e
Compose ha creato i volumi mancanti; PostgreSQL, Redis, API, worker scraper,
frontend e nginx sono attivi. MinIO non è stato avviato perché il registry ha
rifiutato il riferimento preesistente `minio/minio:latest` con “repository
does not exist or may require docker login”; il problema è esterno alla
funzione sviluppata e non è stato aggirato modificando l'infrastruttura.

# Sessione 23 — 14 settembre 2026: controlli Next duplicati equivalenti

La paginazione degli elenchi e quella isolata dei campi accettano ora più
controlli Next quando ogni occorrenza possiede un `href` che, risolto rispetto
alla pagina corrente e senza frammento, conduce alla stessa destinazione. In
modalità browser viene scelto il primo controllo visibile e abilitato, quindi
un duplicato responsive nascosto non blocca quello operativo. L'estrazione
della pagina corrente continua ad avvenire prima dell'avanzamento.

Destinazioni discordanti, selezioni miste link/pulsante e pulsanti JavaScript
multipli continuano a produrre `ambiguous_next_control`; il messaggio spiega
ora la distinzione tra duplicati equivalenti e ambiguità reale. Restano
invariati same-origin, `robots.txt`, rate limit, rilevamento dei loop, limiti e
contratti API. Nessuna migrazione o modifica al formato `scrape_config`.

Verifica finale: Ruff superato; suite backend completa `272 passed`; suite
congiunta del motore HTTP e Playwright `60 passed`; `docker compose config
--quiet` valido. Le immagini API e worker scraper sono state ricostruite e i
due container risultano attivi. La prova live sulla fonte configurata con
`a.page-link[aria-label="Next"]` ha visitato tutte le 20 pagine configurate,
trovato 441 annunci unici e terminato per `max_pages` senza errori né
`ambiguous_next_control`.

Il normale `docker compose up -d --build api worker-scraper` è stato bloccato
dal riferimento preesistente `minio/minio:latest`, rifiutato dal registry; il
collaudo è proseguito costruendo i soli due servizi e avviandoli con
`--no-deps`. Nessun volume applicativo è stato eliminato o ricreato.

# Sessione 24 — 14 settembre 2026: supporto XPath per lo scraper

Ogni selettore della configurazione Sources può ora scegliere autonomamente
tra CSS e XPath 1.0. I nuovi campi camelCase sono
`adLinkSelectorType`, `nextPageSelectorType`, `waitSelectorType`,
`selectorType`, `containerSelectorType`, `keySelectorType`,
`valueSelectorType`, `posterSelectorType`, `videoSelectorType` e
`nextSelectorType`; i valori ammessi sono `css` e `xpath`, con default `css`
per piena compatibilità con tutte le configurazioni precedenti.

Il motore centralizza la selezione degli elementi: Scrapling usa `.css()` o
`.xpath()` nel parsing HTTP e i flussi Dynamic/Stealth usano locator Playwright
con engine XPath esplicito. Testo e attributi `href`/`src` vengono estratti in
modo uniforme. Container e sotto-campi di `keyValue`, `posterVideo` e `items`
possono mescolare i due linguaggi; gli XPath annidati sono relativi al
container tramite sintassi `.//...`. Anche discovery, Next globali, Next dei
campi e wait selector supportano XPath.

Il rilevamento del cambiamento dopo un click non usa più
`document.querySelectorAll`, ma interroga il locator configurato, preservando
timeout, deduplicazione, same-origin, robots, rate limit e gestione dei Next
duplicati equivalenti. Nessuna migrazione DB o nuova dipendenza è necessaria;
duplicazione e import/export continuano a copiare il JSONB completo.

La modale Sources mostra una scelta CSS/XPath per ciascun input e conserva i
tipi durante creazione, modifica, riapertura e prova della bozza. README, API,
architettura, guida sviluppo e `PROGETTO.md` sono stati allineati.

Verifica finale: Ruff superato; suite backend completa `282 passed`, inclusi
24 test browser Playwright; lint frontend senza errori (restano i due warning
Fast Refresh preesistenti), controllo i18n e build Vite superati; E2E Sources
`7 passed` sia sul server di sviluppo sia sul bundle Docker. Le immagini API,
worker scraper e frontend sono state ricostruite; API health HTTP 200, worker
Celery `pong` e `/sources` HTTP 200. Un probe Dynamic nell'immagine API con
wait selector e campo XPath ha estratto correttamente `Example Domain`.
Nessun volume applicativo è stato eliminato o ricreato; i servizi interessati
sono stati avviati con `--no-deps` per non coinvolgere il riferimento MinIO
preesistente non disponibile nel registry.

# Sessione 25 — 16 settembre 2026: ripristino provisioning Grafana

Grafana 13.2.1 poteva entrare in restart loop con `Datasource provisioning
error: data source not found`. La causa era il volume `grafana-data`, creato
quando Prometheus e Loki ricevevano UID automatici, diventati incompatibili
con gli UID stabili `prometheus` e `loki` richiesti dalle dashboard e dagli
alert attuali. Il provisioning dichiara ora `version: 1` per entrambi i
datasource e `prune: true`; non usa `deleteDatasources`, che eliminerebbe e
ricreerebbe inutilmente le sorgenti a ogni avvio. Compose verifica inoltre
`/api/health` prima di considerare Grafana healthy.

Lo script PowerShell `scripts/windows/Recover-Grafana.ps1` opera in sola
diagnostica per impostazione predefinita. Il ripristino esplicito si esegue
dalla root del progetto con:

```powershell
.\scripts\windows\Recover-Grafana.ps1 -Repair
```

Lo script accetta esclusivamente il volume montato su `/var/lib/grafana` con
etichetta Compose `grafana-data`, arresta solo Grafana, salva un archivio in
`backups/grafana`, verifica la presenza di `grafana.db` e solo dopo elimina e
ricrea il volume. Usa `docker compose up -d --no-deps grafana`: PostgreSQL,
MinIO, Prometheus, Loki e gli altri volumi non vengono toccati. Non usare
`docker compose down -v` per questa procedura.

Verifiche successive:

```powershell
docker compose ps grafana
docker compose logs --tail 100 grafana
Invoke-RestMethod http://localhost:3000/api/health
```

Il risultato deve essere `healthy`, il database deve essere `ok` e nei log
non devono comparire errori di provisioning. Per provare l'idempotenza:

```powershell
docker compose restart grafana
docker compose ps grafana
```

## Rollback del volume Grafana

Se occorre ripristinare il database precedente, arrestare e rimuovere soltanto
Grafana, eliminare il solo nuovo volume `grafana-data`, ricrearlo con Compose
e decomprimere al suo interno l'archivio conservato in `backups/grafana` usando
un container temporaneo `grafana/grafana:13.2.1` eseguito come root. Prima di
avviare il vecchio database occorre ripristinare anche la configurazione di
provisioning compatibile con i suoi UID legacy; in caso contrario il restart
loop si ripresenterà. Il backup non va cancellato fino alla verifica completa
di datasource, dashboard e alert.

La sequenza di rollback deve quindi essere eseguita soltanto dopo avere
ripristinato la precedente configurazione versionata: `docker compose stop
grafana`, `docker compose rm -f grafana`, rimozione del solo volume verificato,
`docker compose create --no-deps grafana`, estrazione dell'archivio nel nuovo
volume montato su `/var/lib/grafana` e infine `docker compose start grafana`.
Il nome del volume va sempre ricavato dal mount del container e la sua etichetta
`com.docker.compose.volume` deve essere esattamente `grafana-data`; non usare
nomi presunti, glob o comandi che coinvolgano tutti i volumi.
# Sessione 25 — 17 settembre 2026: evoluzione completa della pipeline

Sono state completate le undici richieste coordinate su fonti, scraping,
contenuti e integrazioni. I media sono sempre visibili senza blur e mantengono
il badge; le fonti hanno Paese ISO opzionale con bandiera, pianificazione
integrata nella modale e limiti globali di pagine/annunci attivabili
separatamente. In assenza dei limiti lo scraper continua fino alla fine reale
della paginazione o a una protezione esistente.

Ogni annuncio conserva `listingPageNumber`; il canonico privilegia pagina più
bassa, priorità fonte, completezza, recenza e ID. La pubblicazione avviene in
batch atomici configurabili (default 50) durante l'acquisizione delle pagine
di dettaglio e committa sempre il resto finale. I batch già pubblicati restano
validi anche se il run si interrompe successivamente.
Gemma via Ollama valuta titolo, descrizione e campi `sanitizeWithAi`, conserva
byte-per-byte i testi puliti, rifiuta output che alterano numeri o fatti e
cifra gli originali. È disponibile un job Admin riprendibile per lo storico.

La pagina Record offre export singolo, selezione, risultati filtrati e intero
archivio; il limite di 1.000 vale solo per gli ID manuali e quello finale resta
2 GiB. Gli scope grandi sono congelati con `INSERT … SELECT`, il worker legge
gli ID con keyset pagination e produce JSON/CSV tramite spool su disco senza
accumulare le righe in RAM. La tab Occorrenze carica su richiesta riepilogo completo, media e
versioni. Le destinazioni webhook hanno CRUD, scope per fonte, politica
telefono, segreto HMAC write-only, payload persistente cifrato e retry dopo
1/5/15/60/240 minuti sulla coda dedicata. Redirect, credenziali URL e target
DNS/IP privati sono bloccati; errori e risposte non persistono contenuti o URL.

I feed proxy HTTPS hanno CRUD, sincronizzazione manuale/periodica, due header
write-only cifrati, limite 5 MiB/50.000 righe e formato
`host:porta:username:password`. Host/porta identificano l'endpoint: porte
diverse sullo stesso IP restano distinte; gli endpoint scomparsi vengono
disabilitati e rimossi dal pool senza cancellarne lo storico. È stata aggiunta
la migrazione additiva `20260917090000_pipeline_integrations.py`; nessun dato
storico viene inventato o sovrascritto.

Sono stati aggiornati README, API, architettura, database, guida sviluppo e
checklist. Il riferimento MinIO non disponibile su Docker Hub è stato
corretto usando le immagini ufficiali Quay per server e client.

Verifica finale: Ruff superato; suite backend completa `290 passed` (118
warning di librerie, nessun fallimento); controllo i18n superato; lint
frontend senza errori (2 warning Fast Refresh preesistenti); build Vite locale
e Docker riuscite; `docker compose config --quiet` e `git diff --check`
validi. La migrazione live è a `20260917090000 (head)`, API health risponde
200 e i cinque worker Celery rispondono `pong`. Prometheus vede UP tutti gli
otto target, Loki riceve log inclusi API e worker webhook, Grafana carica le
tre dashboard provisionate. Frontend, API, scraper, scheduler e worker webhook
sono stati ricostruiti e riavviati. Nessun volume applicativo è stato
eliminato o ricreato.

# Sessione 26 — 18 settembre 2026: barriera automatica per le migrazioni

Un export falliva con `UndefinedColumn` su
`advertisements.listing_page_number`: il codice e le immagini contenevano la
head Alembic `20260917090000`, ma PostgreSQL era ancora alla revisione
`20260909110000`. La correzione consiste nell'applicare integralmente la
migrazione esistente; non vanno aggiunte colonne manualmente.

Compose include ora il servizio one-shot `migrate`, che attende PostgreSQL
healthy ed esegue `alembic upgrade head`. API, scheduler e tutti i worker che
usano il database dipendono da `migrate` con
`condition: service_completed_successfully`: se Alembic fallisce, il codice
incompatibile non parte. Backup, storage e osservabilità restano indipendenti.

Diagnostica ordinaria:

```powershell
docker compose ps -a migrate
docker compose logs migrate
docker compose exec api alembic current
docker compose exec api alembic heads
```

Una seconda esecuzione `docker compose run --rm migrate` deve essere
idempotente. Prima di una migrazione manuale conservare e verificare un dump
PostgreSQL. In caso di errore non usare `alembic stamp`: correggere la causa o
ripristinare il dump, quindi rieseguire il migrator. Non usare
`docker compose down -v`.

Ripristino live completato: il dump
`/backups/lavoro_esterno_20260918_092125.sql.gz` è stato verificato con
`gzip -t`; Alembic ha applicato `20260909110000 -> 20260917090000` e una
seconda esecuzione non ha prodotto modifiche. La catena completa è stata
provata anche su un PostgreSQL temporaneo vuoto. Un test Compose isolato con
migrator volutamente fallito ha confermato che il servizio dipendente non
parte.

Il job export originariamente fallito è stato riaccodato con audit ed è ora
`ready`: ZIP `export-v2` valido, 578 record, 594 occorrenze, campi
`listing_page_number`/`custom_fields` presenti e download presigned HTTP 200.
Ruff e i sei test export/privacy sono verdi; API IPv4 risponde 200 e tutti i
cinque worker Celery rispondono `pong`. Il riavvio di Docker Desktop ha
rigenerato su questa workstation un relay `wslrelay.exe` stale su `::1:80`:
`127.0.0.1` funziona, mentre per ripristinare `localhost` occorre eseguire da
PowerShell elevata `scripts/windows/Repair-Localhost.ps1 -Repair`.

# Sessione 27 — 18 settembre 2026: diagnostica specifica della pulizia Gemma

Il precedente errore unico `content_sanitization_failed — Pulizia del
contenuto non riuscita` è stato suddiviso in cause operative precise:
configurazione mancante/non Gemma, timeout, Ollama irraggiungibile, risposta
HTTP (con status), JSON/schema non valido, campi mancanti, output vuoto,
`changed` non booleano, testo modificato ma dichiarato invariato e numeri
alterati. Ogni causa produce un `errorCode` stabile e un messaggio italiano
che specifica anche l'esaurimento dei tre tentativi.

Le eccezioni di trasporto e le risposte del modello vengono classificate ma
mai copiate nella diagnostica, evitando di esporre URL, prompt o contenuti. Il
job di bonifica storica aggrega inoltre `failures_by_reason` nel risultato e
nell'audit. Verifica: Ruff superato e suite backend completa `292 passed`; i
nuovi test coprono timeout sicuro, risposta incompleta e alterazione dei dati
numerici.

# Sessione 28 — 22 settembre 2026: paginazione browser affidabile

La paginazione JavaScript comune ai mode `dynamic` e `stealth` non usa più un
`element.click()` eseguito nel contesto della pagina. Il worker usa locator
Playwright, click forzato quando il controllo riceve gli eventi e dispatch
diretto quando un overlay lo copre. Dopo il click riacquisisce il DOM e rileva
la transizione tramite URL, link annunci o digest del contenitore; sono inoltre
supportati navigazione completa, aggiornamenti SPA e popup same-origin.

Il generico `browser_pagination_failed` è stato sostituito da cause sicure e
operative (`browser_click_failed`, `browser_navigation_timeout`,
`next_control_detached`, `page_closed`, `browser_closed`,
`cross_origin_popup` e `page_did_not_change`). La pagina Fonti mostra la
descrizione italiana e un suggerimento, senza registrare eccezioni grezze,
URL di navigazione o HTML.

Verifica: Ruff superato; 27 test browser sintetici superati; lint frontend
senza errori (restano due warning Fast Refresh preesistenti); build Vite e
Docker riuscite. Un test live read-only sulla fonte configurata ha visitato
due pagine in modalità `click`, raccolto 43 URL unici e concluso con
`max_pages`, senza errori. API, frontend e worker scraper sono stati
ricostruiti e risultano operativi; health API HTTP 200. Nessun volume è stato
modificato o ricreato.

# Sessione 28 — 18 settembre 2026: prefissi telefonici dal Paese della fonte

La normalizzazione dei telefoni usa ora `phonenumbers` e il codice ISO
selezionato nella fonte. I numeri con prefisso internazionale esplicito `+` o
`00` vengono validati e normalizzati in E.164 senza sostituirne il Paese; ai
numeri nazionali viene aggiunto il calling code della fonte, ad esempio
`3331234567` con `IT` diventa `+393331234567`. Se un numero è locale e la
fonte non ha Paese, l'annuncio viene rifiutato invece di assumere `+39`.

La forma E.164 resta l'input comune di cifratura e HMAC, perciò varianti locale
e internazionale dello stesso numero deduplicano correttamente. Nessuna
migrazione o modifica ai record esistenti. La UI spiega il comportamento sotto
la select Paese; dipendenza e lock sono aggiornati a `phonenumbers 9.0.39`.

Verifica: Ruff superato, suite backend completa `300 passed`, lint frontend
senza errori (due warning Fast Refresh preesistenti) e build Vite riuscita.
Docker Desktop era spento, quindi le immagini non sono state ricostruite e
nessun volume è stato modificato.
