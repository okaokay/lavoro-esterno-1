# Architettura - Lavoro Esterno

## 1. Panoramica

"Lavoro Esterno" è una web app **ad accesso riservato** che raccoglie
annunci pubblicati su diverse fonti (siti di annunci), li **deduplica per
numero di telefono**, arricchisce i dati con classificazione automatica dei
media e riepiloghi generati da AI, e permette la ricerca/esportazione dei
dati raccolti.

Lo stack è containerizzato con Docker Compose ed è composto da:

| Servizio | Ruolo |
|---|---|
| `frontend` | SPA React + Vite + TypeScript + Tailwind, servita in produzione da nginx interno al container (build multi-stage). |
| `api` | Backend FastAPI (Python 3.13), espone `/api/v1/*`, unico punto di accesso ai dati per il frontend. |
| `worker-scraper` | Worker Celery sulla coda `scraping`: esegue i connettori per fonte (uno scraper per sito). |
| `worker-media` | Worker Celery sulla coda `media`: download media, classificazione, generazione anteprime/thumbnail. |
| `worker-ai` | Worker Celery sulla coda `ai`: classificazione contenuti e generazione riepiloghi (LLM). |
| `scheduler` | Celery Beat: pianifica i run periodici degli scraper e task di manutenzione (es. pulizia export scaduti). |
| `postgres` | PostgreSQL 17, database applicativo primario. Solo rete interna. |
| `redis` | Broker Celery + result backend + cache applicativa. Solo rete interna. |
| `minio` | Storage S3-compatible per i media scaricati (immagini/video/thumbnail). Console amministrativa esposta separatamente. |
| `nginx` | Reverse proxy pubblico: unico servizio (con `minio` per la console) esposto all'esterno oltre a instradare verso `frontend` e `api`. |
| `prometheus` | Raccolta metriche (scrape di `api:8000/metrics`). |
| `grafana` | Dashboard e visualizzazione metriche/log, datasource Prometheus+Loki provisionati automaticamente. |
| `loki` | Aggregazione log centralizzata. |
| `alloy` | Discovery dei container del progetto e invio dei log Docker a Loki. |
| `celery-exporter` | Eventi, worker, profondità code e tempi dei task Celery in formato Prometheus. |
| `postgres-exporter` | Metriche operative PostgreSQL. |
| `redis-exporter` | Metriche del broker/cache Redis. |
| `volume-exporter` | Spazio totale/libero dei volumi PostgreSQL e MinIO, montati in sola lettura. |

Tutti i servizi comunicano sulla rete Docker dedicata `lavoro-esterno-net`.
Solo `nginx` (80/443) e `minio` (9000/9001, da restringere in produzione)
pubblicano porte verso l'host; `prometheus`/`grafana` sono esposti per
comodità di accesso diretto in questo setup, ma in un ambiente
esposto pubblicamente andrebbero messi dietro autenticazione/VPN o rimossi
dal `ports:` pubblico (vedi `PROGETTO.md`, sezione Deploy).

## 2. Flusso dati: da annuncio scrapato a record esportabile

```
┌──────────────┐    ┌───────────────┐    ┌────────────────────┐
│  Fonte (sito │───▶│ worker-scraper│───▶│  Normalizzazione    │
│  di annunci) │    │ (coda         │    │  (parsing HTML,     │
│              │    │  "scraping")  │    │  estrazione campi,  │
└──────────────┘    └───────────────┘    │  normalizzazione    │
                                          │  numero telefono)   │
                                          └──────────┬──────────┘
                                                      │
                                                      ▼
                                    ┌─────────────────────────────────┐
                                    │  Deduplicazione multilivello     │
                                    │  1. match esatto su hash HMAC    │
                                    │     del telefono normalizzato    │
                                    │  2. match su varianti telefono   │
                                    │     (prefissi, formati)          │
                                    │  3. euristiche di similarità su  │
                                    │     testo annuncio/città/età     │
                                    └──────────────┬────────────────────┘
                                                   │
                                                   ▼
                                    ┌─────────────────────────────────┐
                                    │  Selezione canonica              │
                                    │  deterministica                  │
                                    │  (regole fisse su recency,       │
                                    │  completezza campi, affidabilità │
                                    │  fonte -> record "canonical_     │
                                    │  history" tracciabile)           │
                                    └──────────────┬────────────────────┘
                                                   │
                          ┌────────────────────────┼───────────────────────┐
                          ▼                                                ▼
              ┌───────────────────────┐                      ┌───────────────────────┐
              │ worker-media (coda    │                      │ worker-ai (coda "ai")  │
              │ "media"): download    │                      │ classificazione        │
              │ media -> MinIO,       │                      │ contenuto + generazione│
              │ classificazione       │                      │ riepilogo (summary_    │
              │ (media_classification_│                      │ versions)              │
              │ history)              │                      │                        │
              └──────────┬────────────┘                      └───────────┬────────────┘
                         │                                               │
                         └───────────────────┬───────────────────────────┘
                                              ▼
                                 ┌─────────────────────────┐
                                 │  Record consolidato      │
                                 │  (searchable via API)     │
                                 └────────────┬──────────────┘
                                              ▼
                                 ┌─────────────────────────┐
                                 │  Esportazione (export_   │
                                 │  jobs -> pacchetto/zip    │
                                 │  con manifest, storage    │
                                 │  temporaneo su MinIO)     │
                                 └─────────────────────────┘
```

Ogni fase scrive tracciabilità: `scrape_runs`/`scrape_errors` per i run
degli scraper, `canonical_history` per le variazioni di selezione
canonica, `media_classification_history` per le rivalutazioni dei media,
`summary_versions` per le rigenerazioni dei riepiloghi AI, `audit_log` per
le azioni utente rilevanti (vedi `docs/DATABASE.md`).

### 2.1 Stato di implementazione reale (vs. diagramma sopra)

Il diagramma descrive il flusso a regime; lo stato implementativo reale,
verificato dal vivo, è più preciso su questi punti (vedi PROGETTO.md § 4):

- **Motore di scraping generico e reale**: `app/scrapers/generic.py:
  GenericScraper` usa Scrapling per richieste HTTP, browser headless e
  modalità stealth configurabile (`fetchMode`) per qualunque fonte con
  `Source.scrape_config` valorizzato — nessuna fonte specifica è hardcoded
  nel motore, i selettori CSS o XPath 1.0 (link annunci, paginazione,
  campi) sono forniti dall'operatore via `PATCH /sources/{id}` o il form
  "Aggiungi/Modifica fonte" nell'interfaccia. Rispetta sempre `robots.txt` (verificato PRIMA
  di ogni richiesta, non solo come check manuale), un rate limit minimo e
  lo User-Agent configurato per la fonte. Se non configurato, HTTP/robots/media
  usano il default del progetto e il browser usa quello generato da Scrapling.
  Dynamic e Stealth mantengono una sessione per run, riusando cookie e storage;
  la rotazione proxy ricrea la sessione per non mescolare identità di rete.
  I campi delle pagine annuncio possono inoltre avere una paginazione isolata:
  il motore visita con il browser gli stati successivi di caroselli o raccolte
  “Carica altri”, deduplica liste semplici o oggetti strutturati e conserva
  risultati parziali con diagnostica sicura quando incontra limiti o errori.
  La risoluzione comune del Next accetta link duplicati in header/footer solo
  quando tutti conducono alla stessa destinazione normalizzata; i controlli
  JavaScript multipli o le destinazioni discordanti restano ambigui.
  Ogni selettore dichiara autonomamente il proprio tipo; Scrapling usa `.css()`
  o `.xpath()` nel parsing HTTP, mentre il browser usa locator Playwright. Le
  configurazioni prive del tipo restano CSS.
  È l'unico motore di scraping del progetto: non esistono più connettori
  Python per-sito precompilati (i 9 stub iniziali descritti nelle versioni
  precedenti di questo documento sono stati rimossi, insieme al
  `registry.py` che li risolveva).
- **Ciclo di vita fonti**: salute (`status`) e attivazione operativa
  (`enabled`) sono distinte. La duplicazione copia configurazione scraper,
  proxy e watermark ma non lo storico, e crea una fonte offline da verificare
  prima della riabilitazione esplicita.
- **Media e classificazione**: lo scraper scarica in streaming, valida e
  persiste soltanto l'originale immutabile; dopo il commit accoda
  `process_media` sulla coda `media`. Il worker genera display/thumbnail
  con FFmpeg/OpenCV e classifica localmente con NudeNet ONNX. Task e stati
  persistenti rendono la pipeline idempotente e ritentabile.
- **Riepilogo AI**: `POST /records/{id}/ai-summary/regenerate` crea un job
  persistente e risponde 202. Il worker `ai` applica budget Redis, cache
  deterministica e OpenAI Responses con Structured Outputs/`store=false`;
  l'API espone lo stato per il polling. Il provider non riceve telefono,
  immagini o URL personali.
- La **deduplicazione** realmente applicata durante l'ingestione è solo
  quella esatta per numero di telefono normalizzato (punto 1
  dell'elenco nel diagramma) — le euristiche di similarità testuale
  (punti 2-3) restano hook non implementati in `app/services/dedup.py`
  (vedi i TODO in quel file).

## 3. Ruolo dei servizi nel `docker-compose.yml`

- **`api`**: espone le rotte REST, applica autenticazione JWT+2FA e RBAC,
  legge/scrive su `postgres`, mette in coda task su Redis (Celery) per gli
  scraper/media/AI, legge/scrive media da/verso `minio`, espone metriche
  Prometheus su `/metrics`.
- **`worker-scraper` / `worker-media` / `worker-ai`**: tre worker Celery
  **separati per coda** (non un unico worker generico), così da poter
  scalare e limitare la concorrenza indipendentemente per tipo di carico
  (lo scraping è I/O-bound e sensibile al rate limiting delle fonti, la
  classificazione media è CPU/GPU-bound, l'AI è sensibile a costi/rate
  limit del provider LLM).
- **`ollama` / `ollama-init`**: runtime LLM interno e inizializzazione
  idempotente di `gemma4:e2b`. Il modello vive nel volume `ollama-data`, la
  porta 11434 non è pubblicata sull'host e `worker-ai` usa concorrenza 1.
- **`scheduler`**: Celery Beat invoca ogni minuto un dispatcher DB-backed.
  Il dispatcher blocca le fonti dovute con `FOR UPDATE SKIP LOCKED`, crea il
  run `pending` prima della pubblicazione e recupera i task non acquisiti.
  La pianificazione è fixed-delay: la nuova scadenza nasce dalla conclusione
  (anche fallita o manuale), mai dall'orario di partenza.
- **`postgres`**: unica fonte di verità relazionale, mai raggiungibile da
  fuori la rete Docker interna.
- **`redis`**: broker/result-backend Celery; se compromesso o perso,
  al più si perdono task in coda/risultati, non dati applicativi.
- **`minio`**: storage oggetti per i media scaricati e per i pacchetti di
  export generati; separato da Postgres per non appesantire il DB con
  blob binari.
- **`nginx`**: termina il traffico pubblico, applica header di sicurezza
  di base, instrada verso `frontend` e `api`; è il solo componente che
  deve essere raggiungibile da Internet in un deploy di produzione (oltre
  eventualmente a TLS terminato a monte, es. da un load balancer/CDN).
- **`prometheus` / `grafana` / `loki`**: stack di osservabilità operativo,
  separato dal dominio applicativo, utile per monitorare salute dei
  worker, tempi di risposta API, errori scraper.
- **Exporter e Alloy**: Prometheus interroga gli exporter interni per Celery,
  PostgreSQL, Redis e volumi; Alloy legge stdout/stderr tramite il socket
  Docker in sola lettura e li inoltra a Loki. Il socket conferisce visibilità
  sui metadati/log di tutti i container dell'host: il filtro
  `OBSERVABILITY_COMPOSE_PROJECT` limita la raccolta a questo progetto, ma in
  produzione l'agente va comunque trattato come componente privilegiato.

### 3.1 Osservabilità e flusso dei segnali

- `GET /metrics` è un endpoint interno, fuori da `/api/v1`, escluso da nginx
  e dall'OpenAPI. Espone metriche HTTP per route normalizzata e aggregati
  DB-backed di `scrape_runs`; un errore DB porta il collector a zero senza
  rendere indisponibili le metriche HTTP.
- Celery pubblica gli eventi `sent`, `started`, `succeeded`, `failed` e
  `retried`; `celery-exporter` li trasforma in contatori/istogrammi e legge la
  profondità delle cinque code dal broker Redis. L'immagine è riprodotta dal
  sorgente 0.12.2 fissato al commit `d45a395e` e verificato via SHA-256, che
  include anche l'istogramma del tempo di attesa in coda.
- Grafana carica automaticamente le dashboard **API Health**, **Celery
  Workers** e **Scraping Sources** e le regole di alert presenti sotto
  `infra/grafana/provisioning/`.
- Le label applicative usano solo UUID/slug della fonte e nomi tecnici di
  servizio/coda: URL, telefoni e messaggi di errore non diventano label.

## 4. Note architetturali specifiche

- **Autenticazione**: JWT (access + refresh token) con 2FA TOTP
  obbligatoria per il ruolo Admin, gestita interamente lato applicativo
  (nessun Keycloak/IdP esterno). Vedi `docs/SICUREZZA.md`.
- **Deduplicazione per telefono**: il numero di telefono non è mai
  salvato/interrogato in chiaro come chiave; si usa un hash HMAC-SHA256
  come indice di lookup e AES-256-GCM per la cifratura del valore
  originale. Vedi `docs/DATABASE.md`.
- **Selezione canonica deterministica**: a fronte di più annunci
  deduplicati sullo stesso numero, un algoritmo con regole fisse (non
  casuali/non-AI) sceglie quale annuncio rappresenta il record
  "canonico" mostrato di default, mantenendo comunque accesso allo
  storico completo.
- **Provider AI runtime**: `ai_settings` sceglie il provider globale e
  `ai_provider_configs` conserva modello, stato, revisione e credenziale
  AES-256-GCM. Ogni job congela provider/modello/revisione; un cambio durante
  l'attesa fa fallire il job esplicitamente invece di cambiarne il modello.
- **Pagina, priorità e canonici**: la pagina di listing più bassa è il primo
  criterio; seguono priorità della fonte, completezza, recenza e ID. I dati
  storici senza pagina vengono dopo quelli con pagina nota. Ogni variazione crea un job sulla coda
  `maintenance`; job duplicati o superati non applicano configurazioni stale.
- **Console operativa**: notifiche persistenti e stato sistema sono esposti da
  endpoint autenticati. I controlli usano timeout brevi, una cache di 10
  secondi e non restituiscono host, credenziali o eccezioni interne.

- **Export isolati**: una coda/worker `exports` con concorrenza 1 genera
  ZIP su disco temporaneo e li carica sotto `exports/{job}/package.zip`.
  Non condivide capacità con media o AI e non include mai originali.
- **Privacy orchestration**: le cancellazioni confermate passano sulla
  coda `maintenance`; la soppressione HMAC viene committata prima di
  eliminare MinIO/DB, rendendo sicuro anche un retry dopo errore parziale.
- **Retention DB-aware**: il task notturno elimina prima gli oggetti,
  invalida gli export derivati e solo dopo modifica il database; un errore
  storage impedisce di dichiarare completata la cancellazione.
## Refresh continuo e rilevamento modifiche

La pipeline di ingestione calcola separatamente il fingerprint deterministico
di titolo/descrizione/campi custom e quello del set di SHA-256 media. Un
riscontro identico aggiorna solo `last_seen_at`; una differenza crea una
revisione immutabile, incrementa `Record.content_revision` e ricalcola il
canonico. Download media parziali non possono far sparire media precedenti.
I riepiloghi AI prodotti su revisioni precedenti vengono segnalati come
obsoleti, senza generazione automatica.

## Acquisizione, sanitizzazione e integrazioni

Il worker scraper associa a ogni URL la pagina di listing, sanitizza con Gemma
titolo, descrizione e soli campi `sanitizeWithAi`, quindi pubblica gli annunci
in batch atomici della dimensione configurata mentre prosegue sulle pagine di
dettaglio. Il resto finale viene sempre committato; retry e upsert sono idempotenti. Gli originali sono cifrati e non
esposti da API, export o webhook.

Alla conclusione di ogni run viene creato un payload webhook persistente. Un
worker dedicato sulla coda `webhooks` consegna solo a URL HTTPS pubblici, con
firma HMAC opzionale, redirect bloccati, politica telefono per destinazione e
retry a 1/5/15/60/240 minuti. Payload e consegne hanno retention 90 giorni.

I feed proxy remoti sono sincronizzati da Celery Beat e dal comando manuale:
download massimo 5 MiB/50.000 righe, protezione SSRF prima e dopo DNS, header
cifrati write-only e riconciliazione non distruttiva degli endpoint del pool.
Gli export `filters` e `all` congelano lo scope con `INSERT … SELECT`; il
worker percorre gli ID con keyset pagination e scrive JSON/CSV su spool su
disco. Resta isolato e applica il limite complessivo di 2 GiB.

La normalizzazione telefonica usa il piano internazionale tramite
`phonenumbers`. Un numero con `+` o `00` viene soltanto validato e convertito
in E.164; un numero nazionale eredita invece il calling code da
`Source.country_code`. La forma E.164 alimenta cifratura e HMAC, quindi la
versione locale e quella già prefissata convergono sullo stesso record.
