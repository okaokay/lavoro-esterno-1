# Guida per sviluppatori - Lavoro Esterno

## 1. Prerequisiti

- Docker e Docker Compose (plugin `docker compose`, non il vecchio
  `docker-compose` standalone).
- Python 3.13 e [uv](https://github.com/astral-sh/uv) (gestione
  dipendenze/venv del backend, usato anche in CI).
- Node.js (versione 20+) e npm (frontend React/Vite/TypeScript).
- Facoltativo per sviluppo locale senza Docker: PostgreSQL 17 e Redis
  installati localmente (in generale è più semplice usare i servizi
  `postgres`/`redis` già definiti nel `docker-compose.yml`).

## 2. Avvio ambiente locale

```bash
# 1. Copiare il file di esempio delle variabili d'ambiente
cp .env.example .env

# 2. Generare le chiavi di cifratura/JWT richieste (valori diversi per
#    ogni sviluppatore/ambiente, non riutilizzare quelli di esempio)
openssl rand -base64 32   # -> PHONE_ENCRYPTION_KEY (deve decodificare a 32 byte)
openssl rand -base64 32   # -> PHONE_HMAC_SECRET
openssl rand -base64 64   # -> JWT_SECRET_KEY (unica chiave, usata sia per access sia per refresh token)
# Incollare i valori generati nel file .env (mai committarlo)

# 3. Costruire e avviare l'intero stack
docker compose up --build

# 4. Le migrazioni sono applicate automaticamente dal servizio one-shot
#    "migrate". API, scheduler e worker restano bloccati se Alembic fallisce.
docker compose ps -a migrate
docker compose logs migrate

# 5. Creare il primo utente Admin: nessun endpoint API può farlo (la
#    creazione utenti via API richiede già un Admin con 2FA attiva), quindi
#    va fatto con questo script una tantum, fuori dal perimetro HTTP/RBAC
#    (vedi backend/app/scripts/create_admin.py per i dettagli):
docker compose exec api python -m app.scripts.create_admin \
    --email admin@lavoro.internal --password "una-password-forte"

# 6. Creare le fonti da scrapare: nessun seed automatico, si usa il CRUD
#    completo via API/UI (POST /sources, form "Aggiungi fonte" nella pagina
#    Fonti — vedi docs/API.md e § 5 sotto). /sources e /search restano
#    vuoti finché non se ne crea almeno una.
```

Questa intera sequenza (`docker compose up --build`, migrator, creazione
admin, login) è stata eseguita ed è stata verificata contro un ambiente
Docker reale: build delle 6 immagini custom, avvio dei 13 servizi (+ 2
servizi di backup, vedi § 8), `POST /api/v1/auth/login` funzionante con la
coppia access/refresh token e l'oggetto `user` atteso dal frontend.

Servizi raggiungibili dopo l'avvio:

- Frontend/API tramite reverse proxy: `http://localhost/`
- Documentazione API interattiva: `http://localhost/docs`
- Console MinIO: `http://localhost:9001`
- Grafana: `http://localhost:3000` (utente `admin`, password da
  `GF_SECURITY_ADMIN_PASSWORD`)
- Prometheus: `http://localhost:9090`

Il bundle Docker usa `VITE_API_URL=/api/v1`: frontend e API sono quindi
same-origin sia tramite `localhost` sia tramite il fallback diagnostico
`127.0.0.1`. Se su Windows `localhost` non risponde ma IPv4 sì, controllare il
relay WSL senza modificare lo stack:

```powershell
.\scripts\windows\Repair-Localhost.ps1
```

Solo dopo aver verificato che lo script identifichi `wslrelay.exe` su
`[::1]:80`, aprire PowerShell come amministratore ed eseguire:

```powershell
.\scripts\windows\Repair-Localhost.ps1 -Repair
```

La riparazione viene rifiutata se nginx IPv4 non restituisce `200`, se il PID
appartiene a un processo diverso o se il percorso non è quello ufficiale di
WSL. Se il relay viene ricreato, usare `wsl --shutdown`, riavviare Docker
Desktop e quindi `docker compose up -d --force-recreate nginx`; non usare
`docker compose down -v`.

Grafana carica automaticamente le dashboard del folder **Lavoro Esterno** e
gli alert. L'endpoint `http://api:8000/metrics` è deliberatamente interno: una
richiesta host a `/metrics` raggiunge il frontend, non FastAPI.

In sviluppo attivo sul frontend, è comune eseguire `npm run dev` in
locale (porta 5173 con hot reload di Vite) invece di ricostruire il
container ad ogni modifica, puntando `VITE_API_URL` all'API esposta dal
reverse proxy o direttamente dal container `api`.

## 3. Migrazioni database (Alembic)

Le migrazioni vivono in `backend/migrations/`. In Docker il servizio one-shot
`migrate` esegue `alembic upgrade head` e costituisce una barriera di avvio:
API, scheduler e worker dipendono dal suo completamento con esito positivo.
Comandi diagnostici e di sviluppo:

```bash
# Stato del migrator e revisione effettiva
docker compose ps -a migrate
docker compose logs migrate
docker compose exec api alembic current

# Esecuzione manuale idempotente, utile per diagnosi
docker compose run --rm migrate

# Creare una nuova migrazione dopo aver modificato i modelli SQLAlchemy
docker compose exec api alembic revision --autogenerate -m "descrizione modifica"

# Verificare la migrazione generata prima di applicarla: l'autogenerate
# di Alembic non è infallibile, va sempre riletta a mano.
docker compose run --rm migrate
```

In locale (senza Docker), equivalente con `uv`:

```bash
cd backend
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "descrizione modifica"
```

## 4. Test

### Backend

```bash
cd backend
uv sync --group dev
uv run ruff check .        # lint
uv run pytest -v           # test (stesso comando usato in CI, vedi .github/workflows/ci.yml)
```

I test che richiedono DB/Redis devono puntare a istanze di test (non a
quelle di sviluppo con dati reali) — usare variabili d'ambiente dedicate
o un container Postgres/Redis effimero, come fatto in CI.

### Frontend

```bash
cd frontend
npm ci
npm run lint
npm run build
# npm run test (se/quando configurato un runner, es. Vitest)
```

## 5. Aggiungere una nuova fonte in `sources`

Il progetto non ha (più) connettori Python per-sito: l'unico motore di
scraping è quello generico configurabile, guidato interamente da
`Source.scrape_config` (§ 6 sotto) — nessun codice da scrivere per
aggiungere una fonte.

- Esiste un CRUD completo via API/UI (`POST /sources`, `PATCH
  /sources/{id}`, `DELETE /sources/{id}`, form "Aggiungi/Modifica fonte" nella
  pagina Fonti — vedi `docs/API.md`) per creare/configurare una fonte. Un
  Admin può duplicarne la configurazione con `POST /sources/{id}/duplicate`:
  la copia non eredita annunci/run e nasce disabilitata. Admin e Operator la
  riattivano con `POST /sources/{id}/enable`.
- Dopo aver creato/configurato la fonte: `POST
  /api/v1/sources/{source_id}/scan` accoda un run reale (coda `scraping`,
  vedi `backend/app/workers/tasks_scraper.py`) — controllare
  `scrape_runs`/`scrape_errors` (o il drill-down nella UI) prima di
  lasciare la fonte attiva su uno schedule. Una fonte senza
  `scrape_config` fallisce esplicitamente il run (nessuna azione
  possibile senza una configurazione).
- Un Admin con 2FA può attivare lo schedule dalla pagina Sources o con
  `PATCH /api/v1/sources/{id}/schedule`. Sono ammessi intervalli tra 15 e
  43.200 minuti. Il primo scan parte dopo un intervallo; quelli successivi
  vengono pianificati dalla fine del run precedente. Il dispatcher Beat gira
  ogni minuto, recupera pending non acquisiti dopo due minuti e chiude come
  falliti i run oltre il limite operativo di sei ore.

Gli Admin possono trasferire le configurazioni dalla pagina Fonti. L'export
produce un JSON versionato per tutte le fonti o per quelle selezionate;
l'import mostra un'anteprima e richiede `Aggiorna` o `Salta` per ogni slug
esistente. Le nuove fonti nascono offline e disabilitate. I pool proxy sono
risolti solo per nome, senza esportare endpoint o credenziali; un pool assente
genera un avviso e lascia la fonte senza associazione. L'import è atomico.

## 6. Configurare il motore di scraping generico

`app/scrapers/generic.py:GenericScraper` esegue scraping REALE tramite
Scrapling (`fetchMode: "http"` per richieste HTTP, `"dynamic"` per browser
headless, `"stealth"` per opzioni anti-bot) per qualunque fonte, guidato da
`Source.scrape_config` — nessun sito specifico è hardcoded nel motore. È
l'unico modo per attivare una fonte, PURCHÉ prima si verifichino ToS/
robots.txt per quel sito specifico (vedi PROGETTO.md § 4 sul perché questo
progetto non lo fa per te).

1. Nel form "Aggiungi fonte" (o via `PATCH /sources/{id}` con `scrapeConfig`),
   fornire: uno o più `startUrls` (pagine di elenco annunci),
   `adLinkSelector` (selettore CSS o XPath dei link ai singoli annunci),
   opzionalmente `nextPageSelector` (paginazione), `fetchMode`,
   `userAgent`, opzioni browser/stealth (`waitSelector`, `waitMs`,
   `solveCloudflare`, `blockWebrtc`, `hideCanvas`, `realChrome`,
   `blockAds`) e i `fields` da estrarre da ogni pagina annuncio
   (selettore CSS/XPath + `attribute` `text`/`href`/`src` + `multiple` per liste
   come le immagini). Un campo `phone` è obbligatorio: senza telefono un
   annuncio non può essere collegato a nessun Record.
   Ogni nome non standard, per esempio `tags`, `city` o `price`, viene salvato
   automaticamente in `advertisements.custom_fields`. Usare `multiple: true`
   per liste semplici. Per caroselli, commenti o recensioni distribuiti su più
   stati della pagina, abilitare la paginazione sul singolo campo indicando il
   selettore del controllo Next/Carica altri, il massimo di pagine (10 di
   default, 50 massimo) e di elementi (1000 di default, 5000 massimo). Questa
   funzione richiede `dynamic` o `stealth`; segue link same-origin o esegue un
   click JavaScript, applicando il rate limit tra le transizioni. La prima
   visualizzazione conta come pagina 1.
   Ogni input selettore ha una scelta indipendente CSS/XPath, serializzata nei
   campi `*SelectorType`; se omessa vale CSS. XPath usa la sintassi 1.0 e deve
   identificare elementi HTML. Nei sotto-campi di `items`, `keyValue` e
   `posterVideo` usare XPath relativi al container come `.//span`, non `//span`.
   Per commenti e recensioni strutturati usare il tipo `items`: il
   `containerSelector` identifica ogni elemento e gli `itemFields` estraggono
   valori scalari relativi come autore, data, voto e testo. Risultati ripetuti
   vengono deduplicati preservando l'ordine; in caso di arresto anomalo il run
   conserva i dati parziali e registra `field_pagination_incomplete`.
   Non serve registrare preventivamente il nome: chiavi arbitrarie come
   `paperino` e `pippo` sono valide e vengono
   preservate esattamente. L'Overview aggrega i valori valorizzati di tutte le
   fonti indicandone la provenienza; la tab Occurrences consente di ispezionare
   lo snapshot originale di ciascuna fonte.
   `realChrome: true` è valido solo con `fetchMode: "stealth"` e usa la
   distribuzione Google Chrome installata nell'immagine backend, distinta dal
   Chromium predefinito. Dopo modifiche al Dockerfile ricostruire almeno API e
   worker scraper con `docker compose up -d --build api worker-scraper`.
2. Usare "Check robots.txt" per verificare che il sito non vieti
   esplicitamente l'accesso (il motore lo verifica comunque ad ogni
   richiesta reale, ma è utile saperlo prima).
3. Usare "Testa configurazione" (`POST /sources/{id}/test-config`, richiede
   la fonte già salvata) per provare la bozza corrente su annunci reali senza
   scriverla nel database e senza usare MinIO. Per la paginazione usare un
   selettore specifico, per esempio `a.page-link[aria-label="Next"]`, non il
   generico `a.page-link`. Sono ammessi più Next in header/footer quando tutti
   gli `href` risolti portano alla stessa pagina; link con destinazioni diverse,
   selezioni miste link/pulsante e pulsanti JavaScript multipli producono
   `ambiguous_next_control`. Il risultato
   mostra pagine visitate, URL annunci unici, modalità `href`/`click` e motivo
   di arresto per l'elenco; `fieldPagination` mostra separatamente pagine,
   elementi, modalità e completezza di ogni campo impaginato. I blocchi
   anti-bot sono distinti dagli errori dei selettori e
   includono azioni operative consigliate.
4. Solo quando l'estrazione di prova è corretta, lanciare uno scan reale
   (`POST /sources/{id}/scan` o il bottone "Avvia scansione" in UI, visibile solo
   quando `hasScrapeConfig` è vero).

Rate limiting (minimo 1s tra le richieste) e rispetto di `robots.txt` sono
applicati SEMPRE dal motore, non sono opzioni disattivabili dalla
configurazione. Se `userAgent` non viene configurato, HTTP, robots e media
usano il default del progetto; i mode Dynamic/Stealth lasciano invece che
Scrapling generi uno User-Agent coerente con Chromium. Una sessione browser
persiste tra listing e annunci, conservando cookie e storage; al cambio proxy
viene chiusa e ricreata. `solveCloudflare` resta best-effort: dopo i tentativi
limitati il run si ferma con `anti_bot_blocked` oppure ruota il pool disponibile.

## 7. Pipeline AI e media

FFmpeg è installato nell'immagine backend/worker. In locale verificare con
`ffmpeg -version`; la suite genera un MP4 sintetico e controlla transcodifica,
thumbnail e frame senza includere materiale sensibile nel repository.

Il default è Ollama locale con `gemma4:e2b`: `ollama-init` scarica il modello
nel volume persistente al primo avvio e il worker AI parte solo al termine.
La configurazione è disponibile in `/settings/ai`. I provider cloud richiedono
una credenziale salvata, un test riuscito e budget token positivo; budget zero
non blocca Ollama. Prima di salvare credenziali generare una chiave AES da 32
byte in base64 e impostarla come `AI_CREDENTIAL_ENCRYPTION_KEY`. Il prompt
corrente è `summary-v2-it`: `summary-v1` conserva il prompt inglese storico;
modificarlo richiede una nuova versione e il
superamento dei test/dataset in `backend/tests/fixtures/summary_eval.json`.

Comandi locali di verifica:

```bash
cd backend
uv sync --group dev
uv run ruff check .
uv run pytest -q
cd ../frontend
npm ci
npm run lint
npm run build
```

`MINIO_PUBLIC_ENDPOINT` deve essere raggiungibile dal browser, mentre
`MINIO_ENDPOINT` resta l'indirizzo interno usato dai container.
`MINIO_REGION` deve coincidere con `MINIO_SITE_REGION` del server (default
`us-east-1`): specificarla consente di firmare gli URL localmente, senza
tentare una richiesta dal container verso l'endpoint pubblico. I task Beat
configurano il lifecycle giornalmente e rimuovono di notte solo oggetti non
referenziati da oltre `MEDIA_ORPHAN_GRACE_HOURS`.

## 8. Retention e backup

Dettagli completi in `docs/DATABASE.md` (§ 5-7). In sintesi:

- **Retention**: un task Celery Beat notturno
  (`app.workers.tasks_maintenance.cleanup_expired_data`) cancella
  `audit_log`/`scrape_errors` più vecchi delle soglie configurate
  (`AUDIT_LOG_RETENTION_DAYS`, `SCRAPE_ERROR_RETENTION_DAYS` in `.env`) e
  libera i pacchetti di export scaduti (`EXPORT_RETENTION_DAYS`). Per
  testarlo manualmente senza aspettare le 3:00 UTC:
  ```bash
  docker compose exec worker-scraper celery -A app.workers.celery_app \
      call app.workers.tasks_maintenance.cleanup_expired_data
  ```
- **Backup**: due servizi sempre attivi nel `docker-compose.yml`,
  `backup-postgres` (dump giornalieri compressi, rotazione
  `BACKUP_RETENTION_DAYS`) e `backup-minio` (replica continua del bucket
  media). Nessuna azione manuale richiesta per farli funzionare; per
  forzare un run immediato (utile in test):
  ```bash
  docker compose exec backup-postgres sh /scripts/backup-postgres.sh --once
  docker compose exec backup-minio sh /scripts/backup-minio.sh --once
  ```
- **Ripristino** (solo manuale, mai automatico):
  ```bash
  docker compose exec backup-postgres ls -la /backups
  docker compose exec backup-postgres sh /scripts/restore-postgres.sh \
      /backups/lavoro_esterno_<timestamp>.sql.gz
  ```

## Convenzioni per commenti e documentazione

Ogni modulo dichiara in apertura la propria responsabilità. Docstring e
commenti interni spiegano soprattutto vincoli di sicurezza, concorrenza,
fallback e decisioni non evidenti; non duplicano istruzioni già leggibili dal
codice. I contratti HTTP fanno riferimento allo schema OpenAPI generato e a
`docs/API.md`. Ogni modifica funzionale deve aggiornare nello stesso commit la
documentazione interessata e, dopo il collaudo, `HANDOFF.md`.

## Verifiche sicurezza

```bash
cd backend
uv run bandit -r app -ll -ii
uv run pip-audit

cd ../frontend
npm audit --audit-level=high
```

Il workflow `.github/workflows/security.yml` aggiunge dependency review,
Trivy su repository/immagini e ZAP baseline/OpenAPI su stack effimero.
High/Critical bloccano la CI; le scansioni ZAP complete girano su schedule
o avvio manuale e pubblicano i report come artifact.

## 9. Observability

Prometheus raccoglie API, Celery, PostgreSQL, Redis, spazio dei volumi, Loki e
Alloy ogni 15 secondi. Le dashboard e le regole sono versionate in
`infra/grafana/provisioning`; non vanno create manualmente dalla UI, perché una
modifica manuale verrebbe sostituita dal provisioning.

Il Celery exporter resta alla versione applicativa 0.12.2, costruita dal commit
`d45a395e` con archivio verificato tramite SHA-256: rispetto alla vecchia image
Docker Hub espone anche `celery_task_queue_wait_time`, usata dalla dashboard.
Alloy assegna ai log le label stabili `compose_project`, `service`, `container`
e `stream=docker`; stdout e stderr sono letti dalla stessa API log Docker.

Alloy seleziona i container tramite la label Compose del progetto. Il default
è `lavoro-esterno-1`; se lo stack viene avviato, ad esempio, con
`docker compose -p staging up`, impostare nello stesso ambiente:

```dotenv
OBSERVABILITY_COMPOSE_PROJECT=staging
```

Il mount read-only di `/var/run/docker.sock` non consente ad Alloy di
modificare direttamente i file dell'host, ma l'API Docker resta un'interfaccia
privilegiata. In produzione limitare l'accesso al container Alloy e non
pubblicare la sua porta.

Diagnostica rapida:

```bash
# Stato dei target e regole Prometheus
curl http://localhost:9090/api/v1/targets
curl http://localhost:9090/api/v1/rules

# Metriche API dall'interno della rete Docker
docker compose exec prometheus wget -qO- http://api:8000/metrics

# Verifica raccolta log e servizi di osservabilità
docker compose logs --tail=50 alloy loki prometheus grafana
docker compose ps celery-exporter postgres-exporter redis-exporter volume-exporter
```

Gli alert bilanciati scattano per API down (2 minuti), coda oltre 100 task
(10 minuti), coda non vuota senza avanzamento (15 minuti), tre fallimenti
scraping consecutivi e spazio libero PostgreSQL/MinIO sotto il 15% (15
minuti). Non è configurato alcun contact point esterno: gli stati firing e
resolved sono consultabili nella sezione Alerting di Grafana.

La retention Loki è di 90 giorni (`2160h`), coerente con
`TECHNICAL_LOG_RETENTION_DAYS`. I dati Prometheus e le posizioni Alloy vivono
nei volumi `prometheus-data` e `alloy-data`; non usare `docker compose down
-v`, che eliminerebbe anche questi dati oltre ai volumi applicativi.

## Proxy rotator

Gli Admin configurano endpoint e pool in `/settings/proxies`, quindi assegnano
il pool nel form Fonte. Elenchi, robots.txt, pagine annuncio e media usano lo
stesso proxy di sessione. Timeout, errori di trasporto e HTTP 403/407/429
causano rotazione; un pool senza endpoint disponibili blocca lo scan senza
fallback diretto.

Per le credenziali impostare `PROXY_CREDENTIAL_ENCRYPTION_KEY` con 32 byte
casuali in base64. Gli host privati sono rifiutati, salvo quelli elencati in
`PROXY_PRIVATE_HOST_ALLOWLIST` (CSV). Il cooldown progressivo e 5/15/30/60
minuti e `PROXY_MAX_ATTEMPTS` vale 3 per default.
## Verificare il refresh continuo

Dopo la migrazione `20260909100000`, due scan identici devono incrementare
`itemsUnchanged` e soltanto i timestamp `last_seen_at`. Modificando titolo,
descrizione, un campo custom o il set media, il run incrementa `itemsUpdated`
e crea una riga in `advertisement_versions`. Il timer automatico resta
fixed-delay: il prossimo intervallo decorre dalla conclusione anche quando il
contenuto non cambia.

## Collaudo della pipeline evoluta

La tab Admin **Acquisizione** configura batch (1–500) e avvia la bonifica
riprendibile dei record storici. Le tab **Webhook** e **Proxy** espongono CRUD,
abilitazione e operazioni manuali; segreti HMAC e valori degli header non sono
mai restituiti dall'API. Per verificare i worker senza modificare i dati:

```bash
docker compose exec api celery -A app.workers.celery_app inspect ping
docker compose exec api alembic current
docker compose config --quiet
```

Durante un test controllato verificare che il run riporti
`listingPageNumber`, che l'ultimo batch sotto soglia sia visibile nei Record,
che i testi puliti restino invariati byte-per-byte e che un webhook produca
una consegna sulla coda `webhooks`. Non usare `docker compose down -v`: il
collaudo non richiede di eliminare o ricreare alcun volume.

Se Gemma rifiuta un annuncio, consultare gli errori del run nella pagina
Fonti. I codici `content_sanitization_*` separano problemi di configurazione,
rete/timeout/HTTP e violazioni del contratto strutturato. Le diagnostiche sono
deliberatamente sicure: non riportano mai il testo sottoposto al modello.

Per i numeri locali configurare sempre il **Paese** della fonte. Il worker
passa il relativo codice ISO a `normalize_phone`; i prefissi espliciti `+` e
`00` hanno precedenza. Se entrambi mancano, l'annuncio viene rifiutato con una
diagnostica sicura invece di assumere automaticamente l'Italia.
