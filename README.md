# Lavoro Esterno

L’interfaccia e i messaggi applicativi sono in italiano. Gli orari sono
visualizzati in `Europe/Rome` e i valori numerici con locale `it-IT`; API,
route e identificatori tecnici restano invariati per compatibilità.

Web app ad accesso riservato per raccogliere annunci da più fonti,
deduplicarli per numero di telefono, arricchirli con classificazione
automatica dei media e riepiloghi generati da AI, e permetterne la
ricerca e l'esportazione controllata.

Stack: React + Vite + TypeScript + Tailwind (frontend), FastAPI su
Python 3.13 con SQLAlchemy 2/Alembic (backend), worker Celery dedicati
per coda (`scraping`, `maintenance`, `media`, `ai`, `exports`, `webhooks`) più uno scheduler (Celery Beat),
PostgreSQL 17, Redis, MinIO (storage media S3-compatible), Nginx come
reverse proxy, Prometheus/Grafana/Loki per l'osservabilità.

L'osservabilità include tre dashboard provisionate (API, worker Celery e
scraping per fonte), alert Grafana, exporter PostgreSQL/Redis/Celery/volumi e
raccolta dei log Docker tramite Grafana Alloy verso Loki. `/metrics` resta
interno alla rete Docker e non viene pubblicato da nginx.

## Documentazione

- [`docs/ARCHITETTURA.md`](docs/ARCHITETTURA.md) - componenti del
  sistema, flusso dati completo (scraping -> deduplicazione ->
  selezione canonica -> media -> AI -> export), ruolo di ogni servizio
  Docker.
- [`docs/API.md`](docs/API.md) - endpoint principali per area
  funzionale, esempi di flusso login+2FA ed export.
- [`docs/DATABASE.md`](docs/DATABASE.md) - schema delle tabelle
  principali e motivazioni di design (in particolare la cifratura del
  numero di telefono).
- [`docs/SICUREZZA.md`](docs/SICUREZZA.md) - autenticazione JWT, 2FA
  TOTP, RBAC, gestione segreti, cifratura, audit log, note GDPR.
- [`docs/SVILUPPO.md`](docs/SVILUPPO.md) - guida pratica per
  sviluppatori (avvio ambiente, migrazioni, test, come aggiungere un
  nuovo scraper/fonte).
- [`PROGETTO.md`](PROGETTO.md) - checklist esaustiva di tutto ciò che
  resta da fare per portare il sistema in produzione.

## Avvio rapido

Prerequisiti: Docker + Docker Compose.

```bash
cp .env.example .env
# Generare le chiavi richieste (vedi commenti in .env.example e
# docs/SVILUPPO.md per il dettaglio), poi valorizzarle in .env:
openssl rand -base64 32   # PHONE_ENCRYPTION_KEY
openssl rand -base64 32   # PHONE_HMAC_SECRET
openssl rand -base64 64   # JWT_SECRET_KEY
openssl rand -base64 32   # PROXY_CREDENTIAL_ENCRYPTION_KEY (se necessaria)

docker compose up --build

# Il servizio one-shot "migrate" applica Alembic prima che API e worker
# possano partire. Verificare che sia terminato con Exit 0:
docker compose ps -a migrate
docker compose logs migrate

# ...creare il primo utente Admin (nessun endpoint API può farlo)
docker compose exec api python -m app.scripts.create_admin --email admin@lavoro.internal --password "una-password-forte"

# ...e creare le fonti da acquisire via API/UI (form "Aggiungi fonte" nella
# pagina Fonti, o POST /sources) — vedi docs/SVILUPPO.md § 5
```

Le modalità browser vengono incluse nell'immagine backend: Chromium è usato
normalmente, mentre l'opzione Sources “Chrome reale” usa Google Chrome tramite
Patchright. Se un'immagine precedente segnala che `/opt/google/chrome/chrome`
non esiste, ricostruire `api` e `worker-scraper` con `--build`.
I campi di una pagina annuncio possono essere impaginati singolarmente in
modalità Dynamic/Stealth per raccogliere caroselli, commenti e recensioni;
sono supportate sia liste di valori sia elementi strutturati configurabili.
Ogni selettore dello scraper può usare CSS oppure XPath 1.0; il tipo si sceglie
separatamente per link annunci, paginazione, attesa, campi e sotto-campi.

La pipeline corrente pubblica gli annunci in batch configurabili dalla tab
Admin **Acquisizione**, ripulisce con Gemma soltanto i testi che richiedono un
intervento e conserva gli originali cifrati. Ogni annuncio registra la pagina
di listing e la selezione canonica privilegia la pagina più bassa. I limiti
globali di pagine e annunci sono opzionali: se non selezionati, lo scraper
prosegue fino alla fine reale della paginazione o a una protezione di sicurezza.
I telefoni con `+` o `00` mantengono il prefisso internazionale; ai numeri
locali viene applicato il prefisso derivato dal Paese selezionato sulla fonte.

Le impostazioni Admin includono inoltre destinazioni webhook filtrabili per
fonte, firmabili HMAC e con politica sul telefono, oltre a feed proxy HTTPS
periodici con due header write-only. La pagina Record consente export singolo,
della selezione, dei risultati filtrati o dell'intero archivio; le occorrenze
espandibili mostrano il dettaglio completo. I media non vengono sfocati, ma
mantengono sempre il badge di classificazione.

Gli Admin possono trasferire le configurazioni tra installazioni dalla pagina
Fonti: l'export produce JSON versionato e l'import mostra sempre un'anteprima
prima dell'applicazione atomica. Le nuove fonti importate restano disabilitate
finché non vengono verificate e attivate manualmente.

Applicazione raggiungibile su `http://localhost/` (reverse proxy nginx),
documentazione API interattiva su `http://localhost/docs`. Sequenza
verificata su un ambiente Docker reale in questa sessione di sviluppo.

Su Docker Desktop/Windows, se `localhost` resta in attesa mentre
`http://127.0.0.1` funziona, eseguire prima la diagnosi non distruttiva:

```powershell
.\scripts\windows\Repair-Localhost.ps1
```

Lo script indica se `[::1]:80` è occupato da un relay WSL non responsivo e
spiega come avviare la riparazione verificata da PowerShell elevata. Non
arresta processi in modalità diagnostica e non elimina volumi Docker.

Per il dettaglio di ogni comando (migrazioni Alembic, test, sviluppo
frontend con hot reload) vedi [`docs/SVILUPPO.md`](docs/SVILUPPO.md).

## Struttura del repository

```
.
├── docker-compose.yml       # Definizione di tutti i servizi dello stack
├── .env.example              # Variabili d'ambiente richieste (template)
├── PROGETTO.md                # Checklist verso la produzione
├── docs/                      # Documentazione tecnica
│   ├── ARCHITETTURA.md
│   ├── API.md
│   ├── DATABASE.md
│   ├── SICUREZZA.md
│   └── SVILUPPO.md
├── infra/                     # Configurazioni di infrastruttura
│   ├── nginx/nginx.conf
│   ├── prometheus/prometheus.yml
│   ├── grafana/provisioning/
│   ├── loki/loki-config.yml
│   ├── alloy/config.alloy
│   └── backup/                # Script backup/restore Postgres + MinIO
├── .github/workflows/ci.yml   # Pipeline CI (lint, test, build immagini)
├── backend/                   # API FastAPI, worker Celery, migrazioni Alembic
└── frontend/                  # SPA React + Vite + TypeScript
```

## Stato del progetto

L'infrastruttura e i flussi principali sono implementati, inclusi scraper
generici con proxy rotator e schedulazione fixed-delay per fonte (il timer
riparte soltanto dalla conclusione dello scan precedente), pipeline media
ONNX/FFmpeg, riepiloghi AI multiprovider, export e flussi GDPR. Restano i gate
di produzione e la validazione esterna. Vedi
[`PROGETTO.md`](PROGETTO.md) per l'elenco dettagliato del lavoro
rimanente.

Le fonti possono essere duplicate dalla UI Admin copiando tutta la
configurazione ma non lo storico; la copia nasce disabilitata. Admin e Operator
possono riabilitare dalla stessa tabella fonti disabilitate o in pausa.

La paginazione dello scraper accetta anche lo stesso link Next ripetuto sopra e
sotto il contenuto: gli `href` devono risolversi alla medesima destinazione.
Controlli con destinazioni diverse o pulsanti JavaScript duplicati vengono
segnalati come ambigui per evitare avanzamenti non deterministici.
