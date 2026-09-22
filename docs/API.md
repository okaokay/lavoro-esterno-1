# API - Lavoro Esterno

Tutte le rotte applicative sono servite sotto il prefisso `/api/v1/`
dall'API FastAPI e sono raggiungibili in produzione tramite il reverse
proxy nginx (`http(s)://<host>/api/v1/...`).

> **Documentazione interattiva**: la lista completa ed esatta di ogni
> endpoint (schema richiesta/risposta, codici di errore, esempi) è
> generata automaticamente da FastAPI ed è disponibile su `/docs`
> (Swagger UI) e `/openapi.json` (schema OpenAPI grezzo). Questo
> documento descrive le **aree funzionali** e lo scopo di ciascun gruppo
> di rotte, da usare come mappa di orientamento; per i dettagli tecnici
> fare sempre riferimento a `/docs`.

## Area `auth` - autenticazione e sessione

| Metodo | Path | Scopo |
|---|---|---|
| POST | `/api/v1/auth/login` | Prima fase: verifica email + password. Se l'utente NON ha 2FA attiva emette subito `access_token`/`refresh_token`/`user` con `status: "authenticated"`; se ce l'ha, risponde `status: "mfa_required"` e un `mfa_token` effimero (nessun token di accesso). |
| POST | `/api/v1/auth/login-2fa` | Seconda fase (solo utenti con 2FA attiva): scambia `mfa_token` + codice TOTP a 6 cifre (o un backup code) con `access_token`/`refresh_token`/`user`. |
| POST | `/api/v1/auth/refresh` | Scambia un refresh token valido con una nuova coppia access/refresh token. |
| GET | `/api/v1/auth/me` | Restituisce profilo, ruolo (Admin/Operator/Viewer) e stato 2FA dell'utente autenticato (richiede `Authorization: Bearer`). |
| POST | `/api/v1/auth/setup-2fa` | Avvia l'attivazione della 2FA per l'utente corrente: genera segreto TOTP, QR code (base64) e i backup codes monouso, mostrati una sola volta. |
| POST | `/api/v1/auth/verify-2fa` | Conferma l'attivazione 2FA fornendo un primo codice TOTP valido generato dall'app authenticator; solo dopo questa chiamata `totp_enabled` diventa `true`. |
| POST | `/api/v1/auth/2fa/backup-codes/regenerate` | Rigenera i backup code dopo verifica TOTP; i codici precedenti diventano inutilizzabili. |
| POST | `/api/v1/auth/change-password` | Cambia password e revoca tutte le sessioni aggiornando il security stamp. |
| POST | `/api/v1/auth/logout` | Revoca in Redis l'access token corrente e, se fornito nel body, anche il refresh token; registra l'audit e risponde `204`. |

I JWT mantengono firma e scadenza stateless, ma la revoca puntuale usa una
blacklist Redis con TTL pari alla vita residua del token. Cambio password,
sospensione e reset 2FA aggiornano invece il security stamp per invalidare in
blocco tutte le sessioni dell'utente.

## Area `dashboard` - viste aggregate per la home

| Metodo | Path | Scopo |
|---|---|---|
| GET | `/api/v1/dashboard/kpis` | KPI aggregati (totale record, fonti attive, nuovi record oggi, errori di scraping, export attivi), con delta/percentuali calcolati per confronto tra finestre temporali adiacenti (nessuno storico snapshot dedicato: vedi commenti in `app/api/v1/dashboard.py`). |
| GET | `/api/v1/dashboard/scraping-activity` | Run di scraping più recenti (`scrape_runs`) joinati con la fonte. |
| GET | `/api/v1/dashboard/source-health` | Conteggio fonti per stato, rimappato sul vocabolario `healthy`/`rateLimited`/`error` (vedi `app/services/source_health.py`). |
| GET | `/api/v1/dashboard/activity` | Attività recente, derivata da `audit_log` (copre solo le azioni esplicitamente audit-loggate, non ogni evento di sistema). |

### Esempio di flusso login + 2FA

1. `POST /api/v1/auth/login` con `{ "email": ..., "password": ... }`.
2. Se l'utente ha la 2FA attiva, la risposta ha `status: "mfa_required"` e un
   campo `mfa_token` (token effimero, non utilizzabile come access token).
3. Il client chiede all'utente il codice a 6 cifre dell'app authenticator e
   chiama `POST /api/v1/auth/login-2fa` con
   `{ "mfa_token": ..., "code": "123456" }` (accetta anche un backup code
   monouso al posto del codice TOTP).
4. In caso di successo la risposta contiene `status: "authenticated"`,
   `access_token` (breve durata, vedi `JWT_ACCESS_TTL_MINUTES`),
   `refresh_token` (durata più lunga, vedi `JWT_REFRESH_TTL_DAYS`) e
   `user` (id/email/name/role/mfa_enabled/status), da usare rispettivamente
   come `Authorization: Bearer <access_token>` e per il rinnovo su
   `/api/v1/auth/refresh`. Nota: `user.name` e `user.status` sono derivati
   (email/`is_active`), non hanno colonne dedicate — vedi `UserPublic` in
   `backend/app/schemas/auth.py`.

## Area `search` - ricerca e consultazione

| Metodo | Path | Scopo |
|---|---|---|
| GET | `/api/v1/search` | Ricerca full-text/filtrata sui record consolidati (per città, età, fonte, intervallo date, presenza media, ecc.). |
| GET | `/api/v1/search/phone` | Ricerca diretta per numero di telefono (calcola l'HMAC lato server e cerca sull'indice, non richiede il numero in chiaro nel DB). |
| GET | `/api/v1/search/suggestions` | Suggerimenti/autocomplete su città, fonti, tag ricorrenti. |

## Area `records` - record consolidati e storico

| Metodo | Path | Scopo |
|---|---|---|
| GET | `/api/v1/records/search` | Ricerca paginata di record con filtri combinabili (`phone`, `source`, `status`, `date_from`, `date_to`, `page`, `page_size`). Il filtro `phone` cerca per hash esatto solo se il valore digitato sembra un numero completo (vedi `app/services/record_search.py`: non esiste ricerca a prefisso su un dato cifrato/hashato). |
| POST | `/api/v1/records/search` | Legacy: lookup esatto di un record dato un numero di telefono completo (hash di lookup). Non usato dal frontend attuale, mantenuto per compatibilità. |
| GET | `/api/v1/records/{record_id}` | Overview di un record per la UI: titolo/descrizione, `tags` aggregati e `customFieldGroups` di tutte le occorrenze con provenienza. `customFields` conserva lo snapshot canonico per compatibilita. |
| GET | `/api/v1/records/{record_id}/occurrences` | Tutti gli annunci (`advertisement`) collegati al record, con flag `isCanonical` e i rispettivi `customFields`. |
| GET | `/api/v1/records/{record_id}/occurrences/{advertisement_id}` | Riepilogo completo di una singola occorrenza: testi ripuliti, fonte/Paese, pagina listing, URL, campi custom, media e metadati. |
| GET | `/api/v1/records/{record_id}/occurrences/{advertisement_id}/versions` | Snapshot immutabili dell'occorrenza, ordinati per revisione e limitati al record richiesto. |
| GET | `/api/v1/records/{record_id}/media` | Media associati agli annunci del record, con classificazione (media non ancora classificato è trattato come "explicit" per default fail-safe). |
| GET | `/api/v1/records/{record_id}/history` | Storico unificato: unione di `canonical_history`, `media_classification_history` e `audit_log` filtrati per il record, ordinati per data. |
| GET | `/api/v1/records/{record_id}/ai-summary` | Ultima versione del riepilogo AI (`summary_versions`); risponde `204` se non è mai stato generato. |
| GET | `/api/v1/records/{record_id}/ai-summary/versions` | Storico COMPLETO delle versioni (non solo l'ultima), più recente prima — per il selettore storico in `RecordAiSummaryTab.tsx`. |
| POST | `/api/v1/records/{record_id}/ai-summary/regenerate` | Crea un job persistente e risponde `202` con `SummaryGenerationJobRead`; il worker usa OpenAI Responses/Structured Outputs. Riservato ad Admin/Operator. |
| GET | `/api/v1/records/{record_id}/ai-summary/jobs/{job_id}` | Stato asincrono `pending`, `processing`, `completed` o `failed`, versione risultante, cache hit ed errore sicuro. |

## Area `sources` - gestione fonti scrapate

| Metodo | Path | Scopo |
|---|---|---|
| POST | `/api/v1/sources/export` | Esporta tutte le fonti o una selezione in un documento JSON portabile e versionato. Solo Admin. |
| POST | `/api/v1/sources/import/preview` | Valida un documento di fonti senza modificarle e segnala nuove fonti, conflitti, errori e pool proxy mancanti. Solo Admin. |
| POST | `/api/v1/sources/import` | Applica atomicamente un documento validato, richiedendo `update` o `skip` per ogni slug esistente. Solo Admin. |
| GET | `/api/v1/sources` | Elenco e stato delle fonti, inclusi `enabled`, metriche recenti e schedulazione (`automaticScrapingEnabled`, intervallo, revisione, ultima/prossima esecuzione e stato `waiting/pending/running/paused/disabled`). |
| GET | `/api/v1/sources/summary` | Conteggio fonti per stato (`total`/`active`/`degraded`/`offline`). |
| GET | `/api/v1/sources/{source_id}` | Dettaglio di una fonte, incluso `scrapeConfig` completo (assente da `GET /sources`, che espone solo il booleano `hasScrapeConfig`) — usato per precompilare il form "Edit configuration". |
| POST | `/api/v1/sources` | Crea una fonte (solo Admin). Accetta `scrapeConfig` e `watermarkRemoval`; quest'ultimo richiede riferimento autorizzativo e almeno una regione normalizzata se abilitato. |
| POST | `/api/v1/sources/{source_id}/duplicate` | Duplica URL, priorità, configurazione scraper/proxy e watermark con nuovo nome/slug. Non copia annunci o run e crea la copia offline/disabilitata. Solo Admin. |
| PATCH | `/api/v1/sources/{source_id}` | Modifica `name`/`baseUrl`/`priority`/`scrapeConfig`/`watermarkRemoval` (solo Admin). Non permette di cambiare `slug`. |
| DELETE | `/api/v1/sources/{source_id}` | Rimuove una fonte (solo Admin). 409 se esistono `advertisement` collegati (storico preservato). |
| POST | `/api/v1/sources/{source_id}/check-robots` | Verifica live il `robots.txt` pubblico della fonte usando lo stesso User-Agent configurato per lo scan — nessun altro contenuto scaricato. Nessuna restrizione di ruolo oltre l'autenticazione. |
| POST | `/api/v1/sources/{source_id}/test-config` | Prova una bozza opzionale `{"scrapeConfig": ...}` senza salvarla; senza body usa la configurazione persistita. Restituisce campione, paginazione e, in caso di errore, `errorCode`, `httpStatus` e `recommendedActions`. Richiede Admin/Operator. |
| GET | `/api/v1/sources/{source_id}/runs` | Storico dei run con origine `manual`/`scheduled`, accodamento, istante pianificato, errori con `errorCode` opzionale e diagnostica di paginazione/proxy. |
| PATCH | `/api/v1/sources/{source_id}/schedule` | Configura il fixed-delay con `enabled`, `intervalValue`, `intervalUnit` e `revision`. Solo Admin con 2FA; intervallo 15 minuti–30 giorni. |
| POST | `/api/v1/sources/{source_id}/pause` | Mette in pausa una fonte (`enabled=false`, status di salute invariato). Riservato ad Admin/Operator. |
| POST | `/api/v1/sources/{source_id}/disable` | Disabilita definitivamente una fonte (`enabled=false`, `status="offline"`). Riservato ad Admin/Operator. |
| POST | `/api/v1/sources/{source_id}/enable` | Riabilita una fonte disabilitata o in pausa (`enabled=true`, `status="healthy"`). Idempotente; riservato ad Admin/Operator. |
| POST | `/api/v1/sources/{source_id}/scan` | Crea un run persistente `pending` e risponde `202`. Restituisce `409` se la fonte ha già un run pending/running; anche il completamento manuale riavvia il timer automatico. |

`countryCode` è il codice ISO associato alla bandiera scelta nella UI. Durante
l'ingestione determina il prefisso dei telefoni nazionali; un numero già
internazionale con `+` o `00` conserva invece il proprio calling code. La
forma persistita e usata per la deduplicazione è E.164.

Gli errori della pulizia Gemma distinguono configurazione, timeout,
indisponibilità, stato HTTP, risposta non valida/incompleta, output vuoto,
indicatore `changed` non valido, testo modificato ma dichiarato invariato e
alterazione dei numeri. `errorMessage` spiega la causa e i tre tentativi senza
includere prompt, testo dell'annuncio, risposta del modello o URL interni.

### Trasferimento configurazioni delle fonti

Il formato `lavoro-esterno-sources` versione `1` contiene `name`, `slug`,
`baseUrl`, `priority`, `scrapeConfig`, `proxyPoolName` e la configurazione
`watermarkRemoval`. Non contiene ID, credenziali proxy, run, metriche,
timestamp, stato o pianificazione. L'export usa `scope: "all"` oppure
`scope: "selected"` con `sourceIds`.

L'import deve essere preceduto dall'anteprima. Lo slug identifica la fonte:
quelle nuove nascono offline, disabilitate e senza schedule; per quelle
esistenti il client sceglie `update` o `skip`. Un aggiornamento conserva stato
e schedule locali. Il pool viene risolto per nome; se manca, l'anteprima
mostra un avviso e l'import rimuove l'associazione. L'intera applicazione usa
una singola transazione, quindi un conflitto concorrente annulla tutte le
modifiche.

### Motore di scraping generico (`scrapeConfig`)

Vedi `PROGETTO.md` § 4 e `docs/DATABASE.md` § "Motore di scraping
generico" per il razionale completo. Struttura di `scrapeConfig` (sia in
`POST`/`PATCH /sources` sia nella risposta di `GET /sources/{id}`):

```json
{
  "startUrls": ["https://example.com/listing"],
  "adLinkSelector": "//article//a[@class='ad-card']",
  "adLinkSelectorType": "xpath",
  "nextPageSelector": "a.pagination-next",
  "nextPageSelectorType": "css",
  "maxPages": 5,
  "maxAdsPerRun": 200,
  "rateLimitSeconds": 2,
  "fetchMode": "dynamic",
  "userAgent": "CustomScraper/2.0",
  "solveCloudflare": false,
  "blockWebrtc": false,
  "hideCanvas": false,
  "realChrome": false,
  "blockAds": false,
  "waitSelector": "//*[@data-loaded]",
  "waitSelectorType": "xpath",
  "waitMs": null,
  "fields": {
    "phone": { "selector": "//span[@class='ad-phone']", "selectorType": "xpath", "attribute": "text" },
    "title": { "selector": "h1.ad-title", "attribute": "text" },
    "tags": { "selector": ".tags span", "attribute": "text", "multiple": true },
    "city": { "selector": ".location", "attribute": "text" },
    "images": {
      "selector": ".gallery img",
      "attribute": "src",
      "multiple": true,
      "pagination": {
        "nextSelector": "button.gallery-next",
        "nextSelectorType": "css",
        "maxPages": 10,
        "maxItems": 1000
      }
    },
    "reviews": {
      "extractionMode": "items",
      "multiple": true,
      "containerSelector": ".review",
      "containerSelectorType": "css",
      "itemFields": {
        "author": { "selector": ".//span[@class='author']", "selectorType": "xpath", "attribute": "text" },
        "rating": { "selector": ".rating", "attribute": "text" },
        "text": { "selector": ".body", "attribute": "text" }
      },
      "pagination": {
        "nextSelector": "button.load-more",
        "maxPages": 10,
        "maxItems": 1000
      }
    }
  }
}
```

Ogni selettore ha un tipo indipendente `"css"` o `"xpath"`: i campi
`adLinkSelectorType`, `nextPageSelectorType`, `waitSelectorType`,
`selectorType`, `containerSelectorType`, `keySelectorType`,
`valueSelectorType`, `posterSelectorType`, `videoSelectorType` e
`nextSelectorType` valgono `"css"` quando omessi. XPath è limitato alla
versione 1.0 e deve selezionare elementi; nei container i sotto-selettori XPath
relativi usano, per esempio, `.//span`. CSS e XPath possono convivere nella
stessa fonte.

Vincoli validati lato server, non aggirabili: il campo `phone` è
obbligatorio in `fields` (senza telefono un annuncio non può essere
collegato a nessun Record); `rateLimitSeconds` ha un minimo di 1 secondo;
`maxPages`/`maxAdsPerRun` hanno un tetto massimo. Il motore usa Scrapling
con `fetchMode: "http"` di default; `"dynamic"` abilita il browser headless
per contenuti generati via JavaScript, `"stealth"` abilita le opzioni
anti-bot di Scrapling configurate sulla fonte. `renderJs` resta accettato
per compatibilità e, se `fetchMode` manca, equivale a `"dynamic"`. Il
motore rispetta sempre `robots.txt`. `userAgent` è opzionale: se assente,
HTTP, robots e media usano il default del progetto, mentre Dynamic/Stealth
lasciano a Scrapling la generazione di uno User-Agent coerente con Chromium.
Le modalità browser riusano la stessa sessione, inclusi cookie e storage, per
tutto il run; la sessione viene ricreata quando cambia proxy.

I codici diagnostici sono `anti_bot_blocked`, `proxy_pool_exhausted`,
`robots_disallowed`, `fetch_failed` e `field_pagination_incomplete`.
`solveCloudflare` esegue tentativi
limitati e non garantisce l'accesso: una challenge ancora attiva interrompe
la richiesta o causa la rotazione sul successivo proxy del pool.

`nextPageSelector` deve identificare un controllo Next univoco oppure più link
duplicati con `href` che, risolti rispetto alla pagina corrente e senza il
frammento, portano tutti alla stessa destinazione. Questo copre, per esempio,
lo stesso Next ripetuto sopra e sotto l'elenco; destinazioni diverse, selezioni
miste link/pulsante e pulsanti JavaScript multipli restano ambigui. Se il
controllo unico non ha `href`, i mode `dynamic` e `stealth` eseguono un click
DOM controllato e attendono che URL o annunci cambino. Il mode HTTP segnala
invece che serve un browser. URL e contenuti già visitati sono bloccati, i link
annuncio sono deduplicati e la navigazione è limitata alla stessa origine.

La `pagination` annidata in un campo è distinta dalla paginazione delle pagine
elenco e richiede `fetchMode` `dynamic` o `stealth`. La prima visualizzazione
conta come pagina 1; `maxPages` vale 10 per default (massimo 50) e `maxItems`
1000 (massimo 5000). Il controllo può essere un link della stessa origine o un
pulsante JavaScript che aggiunge o sostituisce elementi. I valori sono uniti
nell'ordine di prima apparizione e deduplicati. `value` richiede
`multiple=true`; `keyValue` conserva il primo valore per chiave;
`posterVideo` e `items` producono liste. `items` è riservato ai campi custom e
usa `containerSelector` più `itemFields` scalari relativi al container. I
campi standard scalari `phone`, `title` e `description` non possono essere
impaginati; tra i campi standard la funzione è prevista per `images` e
`videos`.

Anche il Next di un campo può comparire più volte, purché tutte le occorrenze
siano link equivalenti secondo le stesse regole della paginazione dell'elenco.

`POST /sources/{id}/test-config` restituisce anche `fieldPagination`, una
mappa per campo con `pagesVisited`, `itemsCollected`, `paginationMode`,
`stopReason` e `complete`. Timeout, loop, navigazioni non consentite e limiti
mantengono i dati già raccolti ma generano la diagnostica
`field_pagination_incomplete` nel run reale.

I nomi diversi dai campi standard `title`, `description`, `phone`, `images`
e `videos` sono campi custom. Lo scan ne salva lo snapshot in
`advertisements.custom_fields`, inclusi valori mancanti (`null`) e liste.
L'Overview espone in `customFieldGroups` ogni campo valorizzato di tutte le
occorrenze, con `sourceId`, `sourceName`, `sourceCode`, `advertisementId` e
`isCanonical`; chiavi con casing diverso restano distinte e valori discordanti
non si sovrascrivono. `tags` e la relativa lista di badge sono aggregati da
tutte le fonti. Il dettaglio Occurrences continua a esporre lo snapshot della
singola fonte. I pacchetti `export-v2` includono lo stesso oggetto in
`advertisements.json` e come JSON deterministico nel CSV.

Una fonte può essere creata senza `scrapeConfig` (`POST /sources` con solo
`name`/`slug`/`baseUrl`) e configurata in un secondo momento via `PATCH
/sources/{id}` quando si decide di attivarne lo scraping reale (previa
verifica ToS/robots.txt per quella fonte specifica) — finché resta senza
configurazione, ogni tentativo di scan fallisce esplicitamente.

## Area `media` - gestione media e classificazione

| Metodo | Path | Scopo |
|---|---|---|
| GET | `/api/v1/media/{media_id}` | Metadati, segnali safety, processing/review state e URL presigned original/display/thumbnail. |
| GET | `/api/v1/media/by-advertisement/{advertisement_id}` | Elenco media di un annuncio con lo stesso contratto esteso. |
| POST | `/api/v1/media/{media_id}/review` | Override manuale `safe`/`explicit` con note, history e audit. Solo Admin/Operator. |
| POST | `/api/v1/media/{media_id}/reprocess` | Reimposta un media fallito/pregresso e accoda la pipeline media; risposta `202`. Solo Admin/Operator. |

Gli URL MinIO sono firmati per pochi minuti e costruiti usando
`MINIO_PUBLIC_ENDPOINT`; non vengono più esposte chiavi oggetto o URL
placeholder. Media `unclassified`, falliti o con `reviewStatus=required`
devono essere presentati dalla UI come sensibili.

## Area `exports` - esportazione dati

| Metodo | Path | Scopo |
|---|---|---|
| POST | `/api/v1/exports` | Crea un job asincrono con scope `selected`, `filters` o `all`. Il limite di 1.000 ID vale solo per `selected`; filtri e archivio completo sono congelati atomicamente nel DB e prodotti con memoria limitata. Limite finale 2 GB. Le richieste legacy con soli `recordIds` o `filters` restano compatibili. |
| GET | `/api/v1/exports` | Storico dei job di esportazione (i più recenti), con richiedente, avanzamento e numero di record. L'URL firmato è emesso solo dall'endpoint di download. Riservato ad Admin/Operator. |
| POST | `/api/v1/exports/{job_id}/retry` | Reimposta un job `failed` a `pending`. |
| GET | `/api/v1/exports/{job_id}/download` | Emette un URL MinIO firmato e auditato per un pacchetto `ready`; risponde `409` se non pronto e `410` se scaduto. |

### Esempio di flusso export

1. `POST /api/v1/exports` con i criteri di ricerca (stessi filtri di
   `/api/v1/search`) e il formato desiderato (es. CSV + media, o solo
   JSON). Risposta: `{ "job_id": "...", "status": "pending" }`.
2. Il job viene eseguito dal worker dedicato sulla coda `exports`, che genera
   un ZIP temporaneo, applica i limiti e lo carica in MinIO.
3. Il client aggiorna `GET /api/v1/exports` finché il job non è `ready` o
   `failed`; non esiste un endpoint di dettaglio separato per il job.
4. A completamento, `GET /api/v1/exports/{job_id}/download` restituisce
   il pacchetto zip (contenente manifest con provenienza dei dati e
   media inclusi) da uno storage temporaneo su MinIO, con scadenza.

## Area `admin` - amministrazione

| Metodo | Path | Scopo |
|---|---|---|
| GET | `/api/v1/admin/users` | Elenco utenti (solo Admin). `name`/`lastLoginAt` sono approssimati (nessuna colonna dedicata nel modello `User`, vedi `app/schemas/admin.py:AdminUserRead`). |
| POST | `/api/v1/admin/users` | Creazione utente con ruolo (Admin/Operator/Viewer). Richiede Admin con 2FA attiva. Risponde con `AdminUserRead` (camelCase, coerente col resto dell'area — bug corretto: prima rispondeva con `UserRead` snake_case, forma diversa da `GET`/`PATCH`/`.../suspend`). |
| PATCH | `/api/v1/admin/users/{user_id}` | Modifica il ruolo di un utente. Richiede Admin con 2FA attiva. |
| POST | `/api/v1/admin/users/{user_id}/suspend` | Sospende un utente (`is_active=false`), impedendo nuovi login. Richiede Admin con 2FA attiva. |
| POST | `/api/v1/admin/users/{user_id}/activate` | Riattiva un utente e revoca definitivamente le sessioni precedenti aggiornando il security stamp. Richiede Admin con 2FA attiva. |
| POST | `/api/v1/admin/users/{user_id}/reset-2fa` | Recovery account: disattiva la 2FA dell'utente (nessun servizio email nel progetto per un reset self-service), che dovrà rifare il setup obbligatorio al prossimo login. Risponde `{ id, mfa_enabled }` (snake_case, NON CamelModel — mappato esplicitamente in `frontend/src/api/admin.ts:resetAdminUserTwoFactor`, stesso stile di `auth.ts`). Richiede Admin con 2FA attiva. |
| GET | `/api/v1/admin/audit-log` | Consultazione dell'audit log (azioni sensibili: login/logout, export, modifiche utenti/fonti, rigenerazione riepilogo AI...). Solo Admin. |
| GET | `/api/v1/admin/ai-settings` | Configurazione globale e provider AI; non restituisce mai le API key. Solo Admin. |
| PATCH | `/api/v1/admin/ai-settings` | Modifica provider attivo e limiti con revisione ottimistica. Admin con 2FA. |
| PATCH | `/api/v1/admin/ai-settings/providers/{provider}` | Salva modello, endpoint custom, opzioni e credenziale cifrata write-only. Admin con 2FA. |
| GET | `/api/v1/admin/ai-settings/providers/{provider}/models` | Catalogo modelli live con cache Redis di cinque minuti. Solo Admin. |
| POST | `/api/v1/admin/ai-settings/providers/{provider}/test` | Test reale di connettività e output strutturato; può consumare quota cloud. Admin con 2FA. |
| GET | `/api/v1/admin/source-priorities` | Fonti, priorità e numero di record interessati, con ultimo job di ricalcolo. Solo Admin. |
| PATCH | `/api/v1/admin/source-priorities/{source_id}` | Cambia priorità e restituisce `202` con un job persistente. Admin con 2FA. |
| GET | `/api/v1/admin/source-priorities/jobs/{job_id}` | Stato e avanzamento del ricalcolo canonico. Solo Admin. |
| GET/PATCH | `/api/v1/admin/classifier-settings` | Modello NudeNet, soglie, revisione ottimistica e statistiche. PATCH richiede Admin con 2FA. |
| POST | `/api/v1/admin/classifier-settings/reprocess` | Riaccoda fino a 1.000 media falliti o in revisione, esclusi gli override manuali. Admin con 2FA. |
| GET | `/api/v1/notifications` | Ultimi alert operativi visibili al ruolo e conteggio non letti. |
| POST | `/api/v1/notifications/{id}/read` | Segna un alert come letto per l'utente corrente. |
| POST | `/api/v1/notifications/read-all` | Segna come letti tutti gli alert visibili. |
| GET | `/api/v1/system/status` | Stato e latenza sanitizzati di API, PostgreSQL, Redis, MinIO, Ollama e worker per coda. |

## Convenzioni generali

- Autenticazione via header `Authorization: Bearer <access_token>` sulle
  rotte applicative. `auth/login`, `auth/login-2fa` e `auth/refresh` ricevono
  invece le credenziali o il token nel body; `/metrics` è intenzionalmente
  senza autenticazione ma resta escluso dal reverse proxy pubblico.
- Autorizzazione RBAC a 3 livelli (Admin/Operator/Viewer): il dettaglio
  dei permessi per ruolo è descritto in `docs/SICUREZZA.md`.
- Paginazione basata sui parametri dichiarati dal singolo endpoint; la ricerca
  record usa `page`/`pageSize`, mentre le liste operative hanno limiti massimi
  espliciti e ordinamento deterministico.
- Tutte le risposte di errore seguono lo schema standard di FastAPI
  (`detail`), consultabile nello schema OpenAPI su `/docs`.

## Proxy rotator

Il proxy non fa parte di `scrapeConfig`: `SourceCreate`, `SourceUpdate` e il
test della bozza accettano `proxyPoolId`. Senza pool la fonte usa la connessione
diretta; con un pool opera fail-closed.

Gli endpoint Admin sono `GET/POST /admin/proxy-pools`, `PATCH/DELETE
/admin/proxy-pools/{id}`, `GET/POST /admin/proxies`, `PATCH/DELETE
/admin/proxies/{id}` e `POST /admin/proxies/{id}/test`. Scritture e test
richiedono 2FA. Le risposte indicano solo `credentialConfigured`, mai le
credenziali. Lo storico run aggiunge `proxyAttemptsCount`,
`proxyRotationsCount` e `proxyStopReason`.

I feed remoti usano `GET/POST /admin/proxy-feeds`, `PUT/DELETE
/admin/proxy-feeds/{id}` e `POST /admin/proxy-feeds/{id}/sync`. Gli header
sono accettati in scrittura ma la lettura restituisce soltanto `headerNames`.

## Acquisizione e webhook

`GET/PATCH /admin/ingestion-settings` legge o aggiorna il batch globale;
`POST /admin/ingestion-settings/sanitize-existing` avvia il job riprendibile
di bonifica Gemma. Le destinazioni si gestiscono con `GET/POST
/admin/webhook-endpoints` e `PUT/DELETE /admin/webhook-endpoints/{id}`. Il
segreto è write-only: la risposta espone solo `secretConfigured`; in modifica
`clearSecret=true` lo rimuove esplicitamente.

## Export e privacy (settembre 2026)

- Gli export usano scope `selected`, `filters` o `all`; le richieste legacy
  senza scope vengono inferite da `recordIds` o `filters`. I filtri supportati
  sono telefono esatto, fonte, stato e intervallo date. L'elenco risolto viene congelato in
  `export_job_records` prima dell'accodamento.
- `GET /exports` mostra tutti i job agli Admin e solo i propri agli
  Operator. `GET /exports/{id}/download` è l'unico endpoint che emette un
  URL firmato ed è sempre auditato.
- `POST /privacy/erasure-requests` crea una bozza con l'impatto stimato;
  `POST /privacy/erasure-requests/{id}/confirm` avvia la cancellazione.
  Lista e dettaglio sono disponibili con `GET` sugli stessi path. Tutta
  l'area è Admin-only e creazione/conferma richiedono 2FA.
- `PATCH /admin/users/{id}` accetta anche `canViewClearPhone`. Il ruolo
  Admin ha il permesso in modo intrinseco; per Operator/Viewer è revocabile.
- Le risposte record espongono `phoneVisibility` (`clear` o `masked`) e
  hanno `Cache-Control: no-store`.
## Aggiornamento continuo delle occorrenze

Ogni scan confronta l'occorrenza identificata da record, fonte e URL. I run
espongono `itemsNew`, `itemsUpdated` e `itemsUnchanged`. Una risposta
occurrence include `revision`, `lastChangedAt` e `hasUpdates`.

`GET /records/{recordId}/occurrences/{advertisementId}/versions` restituisce
gli snapshot immutabili in ordine di revisione decrescente, con soli nomi dei
campi modificati, snapshot corrente e riferimento opzionale al run.

I riepiloghi AI espongono `recordContentRevision` e `isStale`; la
rigenerazione resta esplicita e asincrona.
