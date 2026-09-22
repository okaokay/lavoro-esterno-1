# PROGETTO.md - Checklist per portare "Lavoro Esterno" in produzione

Questo documento elenca in modo concreto tutto ciò che resta da fare per
passare dall'infrastruttura/base creata (docker-compose, documentazione,
CI, scheletro repo) a un sistema pronto per la produzione. Aggiornare le
checkbox man mano che gli elementi vengono completati.

## 1. Autenticazione / 2FA

Tutti i punti sottostanti sono stati implementati e verificati dal vivo
(`docker compose up --build`, non solo test statici): login Admin/Operator
senza 2FA → `mfa_setup_required` con blocco 403 di ogni altro endpoint,
setup+verify 2FA, consumo di tutti e 10 i backup code con auto-rigenerazione
sull'ultimo, riuso di un codice consumato rifiutato, recovery via reset
admin, `change-password` con validazione debole/forte e revoca del refresh
token precedente, `logout` con blacklist del refresh token. Dettagli
implementativi in `docs/SICUREZZA.md`.

- [x] Decidere e implementare la policy MFA per il ruolo **Operator**
      (oggi solo "raccomandata"): obbligatoria da subito, obbligatoria
      dopo N giorni di grazia, o solo Admin — decisione di prodotto.
      **Deciso con l'utente: obbligatoria da subito**, stesso livello di
      Admin. `app/security/deps.py:get_current_user` blocca con 403
      (`error_code: mfa_setup_required`) ogni endpoint applicativo per i
      ruoli admin/operator privi di 2FA attiva, eccetto gli endpoint di
      setup stesso (`get_current_user_allow_unenrolled`). Lato frontend,
      `ProtectedRoute`/`AuthContext` reindirizzano automaticamente a una
      nuova pagina `/2fa-setup` (`TwoFactorSetupPage.tsx`) finché il setup
      non è completato.
- [x] Implementare la procedura di **recovery account** quando un utente
      perde sia il dispositivo TOTP sia i backup codes (oggi previsto
      solo "reset da Admin" a livello di design, manca l'endpoint/flow
      completo e la relativa voce di audit log).
      Nuovo `POST /admin/users/{id}/reset-2fa` (`require_admin_with_2fa`):
      azzera `totp_secret_encrypted`/`totp_enabled`/`backup_codes_hash`,
      aggiorna `security_stamp_at` (revoca ogni token residuo dell'utente),
      audit log `reset_2fa`. Nessun servizio email nel progetto: la
      recovery è admin-driven, l'utente rifà il setup obbligatorio al
      prossimo login (stesso enforcement del punto precedente).
- [x] Definire e implementare la **rotazione/scadenza dei backup codes**
      (quanti codici generare, se rigenerarli automaticamente dopo
      l'uso dell'ultimo).
      Restano 10 codici monouso. Nuovo `POST /auth/2fa/backup-codes/
      regenerate` (rigenerazione manuale, richiede ri-verifica TOTP).
      Rigenerazione **automatica** quando l'utente consuma l'ultimo codice
      rimasto durante `POST /auth/login-2fa`: i nuovi codici sono
      restituiti una sola volta in `new_backup_codes` e mostrati
      dal frontend in un modale bloccante prima di proseguire.
- [x] Implementare **rate limiting sui tentativi di login e di verifica
      TOTP** (protezione da brute force), con blocco temporaneo account.
      Contatori in Redis (`app/security/redis_client.py`, prefisso `auth:`,
      nessuna nuova infrastruttura). Soglie configurabili
      (`LOGIN_MAX_ATTEMPTS`/`LOGIN_LOCKOUT_MINUTES`,
      `MFA_MAX_ATTEMPTS`/`MFA_LOCKOUT_MINUTES`, default 5 tentativi/15
      minuti), applicate a `/auth/login`, `/auth/login-2fa`,
      `/auth/verify-2fa`. Lockout → 429 con `retry_after_seconds`.
- [x] Definire policy di **complessità/scadenza password** (se richiesta
      da requisiti di conformità del cliente).
      **Deciso con l'utente: solo complessità minima, nessuna scadenza.**
      `app/security/password.py:validate_password_strength` (lunghezza
      minima configurabile, varietà di classi di caratteri, denylist
      password comuni, non deve contenere l'email), applicata alla
      creazione utente (`UserCreate`) e al nuovo `POST /auth/
      change-password`.
- [x] Implementare **revoca/blacklist dei refresh token** su logout e su
      cambio password/reset 2FA (richiede storage lato server, es. Redis
      o tabella dedicata).
      Due meccanismi complementari: (1) blacklist Redis del `jti` per
      revoca puntuale su `POST /auth/logout` (access token corrente +
      refresh token se inviato nel body); (2) nuova colonna
      `users.security_stamp_at` (claim `sst` nei JWT, confrontato in
      `get_current_user`/`POST /auth/refresh`) per revoca in blocco di
      *tutti* i token precedenti su cambio password e reset 2FA, senza
      dover tracciare ogni singolo `jti` mai emesso.

## 2. Database / migrazioni

Tutti i punti sottostanti sono stati completati (o esplicitamente valutati
per iscritto, dove la richiesta era "valutare", non "implementare") e
verificati dal vivo (`docker compose up --build`, non solo test statici):
la catena Alembic è stata applicata in sequenza su Postgres reale ed è stata
poi estesa dalle sezioni successive con tabelle e indici operativi; il task
`cleanup_expired_data` è stato eseguito manualmente contro righe
di test con date forzate nel passato (cancellazione selettiva confermata:
solo le righe scadute sparite, quelle recenti intatte; oggetto MinIO di un
export scaduto correttamente "tentato" e l'assenza iniziale del bucket gestita senza
crash), backup Postgres forzato e **ripristinato con successo sullo stesso
database popolato** (`pg_dump --clean --if-exists` + `psql`, dati e indici
intatti dopo il restore), backup MinIO forzato (comportamento corretto anche
in assenza iniziale del bucket). Nel farlo è stato trovato e corretto un bug pre-esistente non
di questa sezione ma scoperto qui: `GET /sources` restituiva
`itemsLast24H` (H maiuscola) invece di `itemsLast24h` per un difetto di
`pydantic.alias_generators.to_camel` sui confini cifra/lettera — non era
mai emerso prima perché la lista fonti era sempre stata vuota nei test
precedenti. Corretto con un alias esplicito in
`backend/app/schemas/sources.py`. Dettagli implementativi/motivazioni in
`docs/DATABASE.md`.

- [x] Scrivere le migrazioni Alembic iniziali per tutte le tabelle
      descritte in `docs/DATABASE.md` (record, advertisement, media,
      sources, canonical_history, scrape_runs, scrape_errors,
      media_classification_history, summary_versions, export_jobs,
      audit_log, users). — fatto e verificato dal vivo (`alembic upgrade
      head` crea le 12 tabelle su Postgres reale, vedi sezione 12).
- [x] Definire e creare gli **indici** definitivi oltre a quelli minimi
      già identificati. Nota: il punto citava "città + data" come esempio,
      ma `advertisement` non ha un campo città (schema reale verificato,
      non inventato ora) — sostituito con indici che mappano su colonne
      esistenti e query reali: composito `advertisements(source_id,
      status)`, GIN full-text su `advertisements` (title+description),
      `media(perceptual_hash)`, composito `export_jobs(status,
      requested_at)`, `export_jobs(requested_by_user_id)`,
      `scrape_errors(created_at)`, `audit_log(created_at)` — migrazione
      `backend/migrations/versions/20260829091500_additional_indexes.py`,
      applicata con successo su Postgres reale.
- [x] Definire la **retention policy per categoria di dato** e
      implementarla come task periodico dello scheduler. I default
      configurabili sono annunci 365gg, media 180gg, run/errori tecnici 90gg,
      notifiche 90gg, audit 365gg ed export 7gg; `0` disabilita la categoria.
      I valori definitivi restano soggetti alla validazione legale/GDPR (vedi
      sezione 8). Task
      `app.workers.tasks_maintenance.cleanup_expired_data`, schedulato
      ogni notte alle 3:00 UTC, eseguito sulla coda `maintenance` del
      worker `worker-scraper` (nessun servizio Celery dedicato).
- [x] Configurare **backup automatici** di PostgreSQL e di MinIO, in
      forma locale/Docker Compose riutilizzabile (dipendenza dall'ambiente
      di hosting definitivo confermata, quindi non un backup off-site):
      due nuovi servizi `backup-postgres` (dump giornaliero compresso +
      rotazione, `infra/backup/backup-postgres.sh`) e `backup-minio`
      (replica continua del bucket, `infra/backup/backup-minio.sh`), su
      volumi dedicati `postgres-backups`/`minio-backups`. Test di
      ripristino reso eseguibile (non automatizzato, è un'operazione
      distruttiva) con `infra/backup/restore-postgres.sh`. Da adattare a
      un target remoto quando si sceglie l'hosting definitivo.
- [x] Valutare **partitioning** delle tabelle ad alto volume
      (`advertisement`, `scrape_errors`): valutazione scritta, senza
      implementazione anticipata; vedi `docs/DATABASE.md` § 7 per soglie
      indicative e costo di conversione di una tabella esistente.
- [x] ~~Popolare un **seed di sviluppo** per le 9 fonti previste~~ —
      **rimosso in un secondo momento** insieme ai 9 connettori stub e a
      `registry.py`: le fonti si creano ora solo via API/UI, nessun seed
      automatico (vedi `docs/SVILUPPO.md` § 5).

## 3. Frontend

Tutti i punti sottostanti sono stati implementati e verificati dal vivo
(`docker compose up --build`, `npx playwright test` contro lo stack reale,
non solo test statici). Due piccoli endpoint backend sono stati aggiunti
per supportare onestamente i requisiti (storico versioni Riepilogo AI,
storico run per fonte) invece di limitare la UI ai dati già disponibili —
vedi `docs/API.md`. Durante la verifica sono stati trovati e corretti 3 bug
reali (dettagli nelle note dei singoli punti e in `docs/API.md`).

- [x] Rifinire la pagina/tab di **Accesso + 2FA**: `describeError()`
      (`src/lib/errors.ts`, nuovo) legge `retry_after_seconds` dal body
      429/403 del backend; countdown live (`useCountdown`,
      `src/hooks/useCountdown.ts`) che disabilita il submit fino a fine
      lockout, sia sullo step password sia sullo step codice, sia sul
      setup 2FA iniziale. Messaggio distinto "Too many attempts" vs
      credenziali/codice errati. Verificato dal vivo con login reali
      (password errata, codice TOTP errato, login completo con codice
      TOTP generato a runtime nei test E2E).
- [x] Rifinire la pagina/tab di **Ricerca**: filtri sincronizzati con la
      query string (`useSearchParams`, sopravvivono al refresh), opzione
      "Origine fonte" popolata da `GET /sources` (prima 3 valori inseriti nel codice
      mai esistiti: `web`/`forum`/`manual`), errori di rete uniformati
      (`ErrorRow error={...} onRetry={...}`). Paginazione a pagine
      numerate mantenuta deliberatamente (volume atteso non giustifica
      infinite scroll).
- [x] Rifinire la pagina/tab di **Dettaglio Record**: Riepilogo AI ha ora
      un selettore storico versioni (nuovo endpoint `GET /records/{id}/
      ai-summary/versions`, prima il backend esponeva solo l'ultima); gli
      eventi "Cambio annuncio canonico" nello storico sono ora
      visivamente distinti (icona/bordo/badge dedicati) dagli altri eventi
      generici; galleria media già mostrava lo stato di classificazione,
      solo uniformata la gestione errori.
- [x] Rifinire la pagina/tab di **Gestione Fonti**: righe espandibili con
      drill-down storico run + errori per fonte (nuovo endpoint `GET
      /sources/{id}/runs`, prima assente: solo `errorRate` aggregato era
      visibile); azioni Run/Pause/Disable nascoste lato client per il
      ruolo Viewer (il backend le rifiutava già con 403, qui solo UX).
- [x] Rifinire la pagina/tab di **Esportazioni**: polling automatico
      (`refetchInterval` TanStack Query, ogni 3s solo se esiste un job
      `processing`) in aggiunta al refresh manuale già presente.
- [x] Rifinire la pagina/tab di **Amministrazione utenti**: form "Create
      user" (`POST /admin/users`) e bottone "Reset 2FA" per riga (`POST
      /admin/users/{id}/reset-2fa`) collegati per la prima volta in UI
      (gli endpoint backend esistevano già, inutilizzati). Bug trovato e
      corretto durante il collegamento: `POST /admin/users` rispondeva con
      uno schema diverso (`UserRead`, snake_case) da tutti gli altri
      endpoint dell'area (`AdminUserRead`, camelCase) — il form avrebbe
      letto `undefined` per `name`/`status`/`mfaEnabled`. Trovato anche e
      corretto durante la verifica manuale: i testi dei nuovi dialog
      "Create user"/"Reset 2FA" erano stati scritti in italiano
      dall'agente che li ha implementati, incoerenti con il resto
      dell'interfaccia (interamente in inglese) — tradotti.
- [x] Rifinire la pagina/tab di **Audit log**: filtri client-side per
      attore/azione (substring) e range data sui record già scaricati
      (l'endpoint `GET /admin/audit-log` non supporta query param di
      filtro, non esteso in questa fase).
- [x] Gestione uniforme degli **stati di errore**: nuovo
      `src/lib/errors.ts` (`describeError`, mappa 403/404/429 con
      `retry_after_seconds`/5xx/errore di rete su titolo+descrizione+
      retryable) e nuovo componente condiviso `src/components/ui/
      ErrorState.tsx`; `ErrorRow` (`src/components/ui/Table.tsx`) esteso
      per accettare lo stesso pattern dentro le tabelle. Applicato a tutte
      le pagine/tab, sostituendo la gestione ad-hoc precedente (stringhe
      fisse per pagina, nessun retry).
- [x] Passata di **accessibilità**: `Dialog` (`src/components/ui/
      Dialog.tsx`) ora ha focus trap (Tab/Shift+Tab vincolati dentro il
      modale), chiusura con Escape, ripristino del focus precedente alla
      chiusura, `aria-labelledby` sul titolo — verificato dal vivo (focus
      dentro il dialog all'apertura, dialog chiuso da Escape). Aggiunte
      `aria-label` mancanti sui bottoni icon-only del Topbar. Label dei
      filtri di Ricerca collegate ai controlli (`htmlFor`/`id`, prima
      erano `<label>` senza associazione programmatica — un vero difetto
      di accessibilità, non solo un problema di test). Contrasto colori
      verificato a vista sulla palette dark (§ punto successivo), nessun
      fallimento evidente.
- [x] Implementare **dark mode**: tutti i ~40 token colore convertiti da
      valori hex statici a variabili CSS (`src/index.css`, pattern
      `rgb(var(--color-x) / <alpha-value>)`), con un blocco `.dark`
      completo che copre l'intera palette (ruoli Material-3 "fixed"
      esclusi, identici per design in entrambi i temi) — questo evita di
      dover aggiungere varianti `dark:` a ogni classa Tailwind esistente.
      `ThemeContext` (`src/context/ThemeContext.tsx`, nuovo) con
      preferenza `light`/`dark`/`system` persistita in `localStorage`,
      applicata prima del primo paint via script inline in `index.html`
      (evita flash del tema sbagliato). Toggle nel Topbar. Verificato dal
      vivo: toggle applica `html.dark`, persiste al reload, sfondo
      effettivamente cambiato (RGB confermato via script).
- [x] Test end-to-end sui 3 flussi critici con **Playwright**
      (`frontend/e2e/`, `playwright.config.ts`): login+2FA (incluso un
      generatore TOTP nativo in `e2e/totp.ts`, nessuna dipendenza
      aggiuntiva, verificato produrre lo stesso codice di `pyotp`),
      ricerca, export. **Eseguiti realmente** con `npx playwright test`
      contro lo stack Docker live (non solo scritti): 8/9 passati, 1
      skippato correttamente (nessun export "ready" esiste ancora in
      questo ambiente, atteso finché il worker reale non è implementato,
      vedi § 7).

### Aggiornamento interfaccia e console operative — 4 settembre 2026

- [x] Record e Ricerca unificati in `/records`; `/search` resta un reindirizzamento
      compatibile che conserva la query string. L'elenco è paginato anche
      senza filtri e “Tutte le fonti” non blocca più la richiesta.
- [x] Riepilogo AI interpreta correttamente `204 No Content` come assenza del
      riepilogo, senza passare `undefined` a React Query.
- [x] Utenti sospesi riattivabili da Admin con 2FA e revoca delle vecchie
      sessioni; protette auto-sospensione e sospensione dell'ultimo Admin.
- [x] Pagina `/account` collegata dall'header con cambio password, setup 2FA e
      rigenerazione monouso dei backup code. Profile e Support sono rimossi.
- [x] Console Priorità fonti con job asincrono persistente e scelta canonica
      basata su priorità, completezza, recenza e ID, senza eccezioni per slug.
- [x] Console Classifiers con soglie NudeNet revisionate, statistiche e
      riaccodamento bulk che preserva gli override manuali.
- [x] Notifiche operative persistenti con RBAC, deduplicazione, ricevute di
      lettura e retention di 90 giorni; pannello System Status con timeout,
      cache breve e risultati sanitizzati.

## 4. Scraper per fonte

**Cambio di approccio rispetto alla formulazione originale di questa
sezione** (che chiedeva selettori hardcoded per le 9 fonti sotto): è stato
costruito un **motore di scraping generico e reale**
(`backend/app/scrapers/generic.py:GenericScraper`) — fetch e parsing HTML
via Scrapling, nessun sito specifico conosciuto dal motore. La conoscenza
del sito (URL, selettori CSS o XPath 1.0 per
link annunci/paginazione/campi) è fornita dall'operatore tramite l'app
(`PATCH /sources/{id}` o il form "Aggiungi/Modifica fonte" nell'interfaccia), non scritta da
chi ha sviluppato il progetto. Motivazione: implementare selettori reali
per queste 9 fonti specifiche (siti commerciali di annunci di servizi
sessuali) avrebbe significato raccogliere sistematicamente numeri di
telefono e media di persone reali senza possibilità di verificare
un'autorizzazione legale o una finalità legittima — un rischio concreto
di abilitare stalking/doxxing/molestie verso una popolazione vulnerabile,
indipendentemente dal contesto d'uso dichiarato. Per questo le 9 checkbox
per-fonte restano non spuntate: il lavoro rimanente per ciascuna è ora
"verificare ToS/robots.txt e trovare i selettori CSS/XPath giusti", non più
"scrivere codice" — vedi `docs/SVILUPPO.md` § 7 per la procedura completa
(Controlla robots.txt -> Testa configurazione su un annuncio reale, senza
scrivere su DB -> scan reale).

- [x] Rendere configurabile lo **User-Agent** dello scraper per singola
      fonte: `scrapeConfig.userAgent` è opzionale e, se assente, il motore
      usa il default `Scraper.user_agent`
      (`backend/app/scrapers/base.py`). Lo stesso valore viene usato da
      Scrapling, download media e verifica `robots.txt`.
- [x] Rendere persistente la sessione browser Scrapling per ogni run, con
      riuso di cookie/storage, User-Agent browser automatico quando non
      configurato e diagnostica `anti_bot_blocked` dopo i tentativi limitati.
- [x] Supportare l'**impaginazione interna dei campi** delle pagine annuncio:
      caroselli e raccolte di commenti/recensioni seguono link o controlli
      JavaScript per campo, con liste semplici o elementi strutturati,
      deduplicazione, limiti e conservazione diagnostica dei risultati parziali.
- [x] Dashboard/alert per **fonti che smettono di funzionare**:
      `consecutiveFailures` in `GET /sources` (run consecutivi falliti,
      dati già in `scrape_runs`), badge "Connector broken?" in UI quando
      >= 3 (`CONSECUTIVE_FAILURES_ALERT_THRESHOLD`,
      `backend/app/api/v1/sources.py`). Solo alert visivo in-app: nessun
      canale di notifica esterno (email/Slack) esiste nel progetto (vedi
      § 9 Observability).
- [x] **Motore di scraping generico reale**, configurabile per fonte
      dall'applicazione (URL di partenza, selettore link annunci,
      paginazione, campi da estrarre, `fetchMode` HTTP/dynamic/stealth e
      opzioni Scrapling) — vedi sopra. Rispetta SEMPRE
      `robots.txt` (verificato prima di ogni richiesta, non solo come
      check manuale — `app/services/robots_check.py`) e un rate limit
      minimo di 1s tra le richieste, non disattivabili da configurazione.
      Collegato alla pipeline reale di ingestione
      (`app/services/scrape_ingest.py`): dedup per telefono, upsert
      annunci, upload media su MinIO, ricalcolo canonico — la PRIMA
      pipeline di scraping->persistenza end-to-end del progetto.
- [x] **CRUD completo per le fonti dall'applicazione**: `POST/PATCH/
      DELETE /sources`, form "Aggiungi/Modifica fonte" nell'interfaccia (solo Admin per
      creazione/modifica/eliminazione; eliminazione bloccata con 409 se
      esistono annunci collegati). Unico modo per creare una fonte oggi:
      i 9 connettori stub e lo script di seed sono stati rimossi in un
      secondo momento (vedi nota sotto).
- [x] **Import/export configurazioni fonti**: documento JSON versionato per
      tutte le fonti o una selezione, senza ID, stato operativo o credenziali
      proxy. L'import Admin mostra un'anteprima, risolve i conflitti per slug
      con aggiornamento/salto ed è applicato in una sola transazione. Le fonti
      nuove nascono offline e disabilitate; i pool sono associati per nome.
- [x] **Verifica `robots.txt`**: enforcement automatico nel motore (sopra)
      + strumento di verifica manuale in UI (`POST /sources/{id}/
      check-robots`, scarica solo il file pubblico `robots.txt`, nessun
      altro contenuto della fonte).

- [x] **Proxy rotator globale**: pool riutilizzabili amministrati con 2FA,
      selezione least-recently-used, credenziali AES-256-GCM, cooldown passivo,
      test manuale e policy fail-closed. Listing, annunci e media condividono
      il proxy di sessione; gli errori ritentabili ruotano fino a tre endpoint.
- [x] **Scraping automatico fixed-delay per fonte**: intervallo configurabile
      Admin/2FA tra 15 minuti e 30 giorni. Il timer parte dalla conclusione del
      run precedente (anche manuale o fallito); run persistenti `pending`,
      dispatcher Celery Beat, recupero pubblicazioni e vincolo DB assicurano
      che una fonte non abbia mai due scan pending/running contemporanei.
- [x] **Aggiornamento continuo e versionato delle occorrenze**: ogni scan
      confronta titolo, descrizione, JSON custom e set SHA-256 dei media per la
      terna record/fonte/URL. Un contenuto identico aggiorna soltanto
      `last_seen_at`; una modifica incrementa le revisioni, crea uno snapshot
      in `advertisement_versions`, aggiorna il canonico e rende obsoleto il
      riepilogo AI precedente. I download parziali non rimuovono media e gli
      annunci assenti da un run non vengono marcati rimossi.

**Nota successiva (rimozione dei 9 connettori stub)**: i 9 connettori
Python per-sito descritti nella sezione seguente e il loro
`app/scrapers/registry.py` sono stati eliminati dal codice in un secondo
momento, su richiesta esplicita — non restavano comunque implementabili
per le ragioni di sicurezza spiegate sotto, quindi tenerli come stub morti
nel repository non aggiungeva valore. L'unico motore di scraping oggi è
quello generico (`GenericScraper`), a cui va associata esplicitamente
qualunque fonte tramite `scrape_config` prima di poterla scansionare.

**Verificato dal vivo** (Docker reale, non solo test): creata una fonte di
test via `POST /sources` puntata a un piccolo server HTTP locale
sintetico (fixture scritte da zero, non un sito reale — le stesse usate
dai test pytest in `backend/tests/scrapers/`), verificato `check-robots`
e `test-config`, eseguito uno scan reale (`POST /sources/{id}/scan`) che
ha davvero scaricato le pagine con rate limiting (~1s tra le richieste),
creato 2 `Record`/`Advertisement` reali (il terzo annuncio di test, senza
telefono, correttamente scartato), caricato 2 media reali su MinIO
(verificato con `list_objects`), impostato `canonical_ad_id`. Verificato
anche il blocco 409 su `DELETE` con annunci collegati, poi eliminazione
riuscita dopo aver rimosso i dati di test. 9 test pytest nuovi
(`backend/tests/scrapers/test_generic_scraper.py`) contro le stesse
fixture sintetiche via un vero server HTTP locale (nessuna rete reale),
incluso un test che verifica che un `robots.txt` con `Disallow: /` blocchi
DAVVERO il motore (non solo in teoria) + 8 test di validazione schema
(`backend/tests/test_sources_schemas.py`) — suite completa a 85/85.

Bug pre-esistente trovato e corretto in questo passaggio: la colonna
"Priorità" della tabella Fonti nell'interfaccia mostrava in realtà un'etichetta
High/Medium/Low derivata da `errorRate` (il campo `priority` non era mai
stato esposto da `GET /sources`) — il tasso di errore travestito da
priorità. Corretto aggiungendo `priority` allo schema `SourceRead`.

## 5. AI / classificazione media

- [x] **Classificazione ONNX reale** con NudeNet 3.4.2/320n, modello
      caricato in modo lazy nel worker media e versione persistita come
      `nudenet-3.4.2-320n`. Le immagini sono analizzate direttamente; per
      i video si aggrega il rischio massimo di cinque frame al
      10/30/50/70/90%. I segnali salvati includono punteggio esplicito,
      volto, watermark e `possibleMinorReview`. Quest'ultimo è solo un
      escalation flag quando coesistono contenuto esplicito e volto: non
      viene mai stimata automaticamente l'età.
- [x] **Soglie e revisione umana prudenziale**: `explicit >= 0.65`,
      `safe < 0.20`, fascia intermedia/errori `unclassified`; contenuti
      non classificati o con escalation restano sensibili. Admin e
      Operator possono effettuare override motivato tramite
      `POST /media/{id}/review`; autore, note, history e audit sono
      persistiti. È disponibile anche `POST /media/{id}/reprocess`.
- [x] **Riepiloghi asincroni multiprovider** con Ollama locale, OpenAI,
      Anthropic/Claude, Google Gemini, Groq, Mistral, OpenRouter e un endpoint
      OpenAI-compatible personalizzato. Il default è `gemma4:e2b` locale;
      provider, modello, credenziali cifrate e limiti sono amministrabili da
      `/settings/ai`. OpenAI conserva Responses API, Structured Outputs e
      `store=false`. Non esistono fallback silenziosi tra modelli/provider.
- [x] **Minimizzazione e gestione costi**: telefoni e URL vengono redatti
      anche dai campi testuali; immagini e URL sorgente non sono inviati
      al provider e i riferimenti interni vengono rimappati localmente.
      Redis applica limite giornaliero utente e requests/minute per provider;
      per i provider cloud applica anche budget token con prenotazione e
      riconciliazione. Budget cloud zero blocca solo i provider remoti, non
      Ollama locale.
- [x] **Cache/versioning/evaluation**: `summary-v1`, provider, modello,
      hash deterministico, token input/output/cache e job sono salvati in
      `summary_versions`; un vincolo univoco evita versioni duplicate e
      abilita cache hit senza chiamata. Dataset sintetico/redatto e test
      verificano schema, riferimenti interni, minimizzazione e stabilità.

Verifica automatica: inferenza NudeNet reale su immagine innocua, adapter AI
simulati, cifratura credenziali, schema Ollama e suite completa. I test live
dei provider cloud restano opt-in e richiedono credenziali e budget dedicati.

## 6. Storage / media

- [x] **Watermark autorizzato per fonte**, disabilitato per default. Solo
      Admin può abilitarlo fornendo riferimento autorizzativo e almeno
      una regione normalizzata valida. OpenCV inpaint elabora immagini e
      FFmpeg `delogo` i video; l'originale è immutabile e l'operazione è
      registrata nell'audit.
- [x] **Pipeline FFmpeg reale** nel worker media: output MP4 H.264/AAC,
      `yuv420p`, faststart, CRF 23, massimo 1280x720; thumbnail JPEG max
      640 px e cinque frame per classificazione. Comandi senza shell
      interpolation, timeout e directory temporanee isolate.
- [x] **Download/validazione controllati**: solo HTTP(S), redirect
      rivalidati, blocco SSRF verso IP privati/reserved, streaming con
      limite e controllo Content-Length/risposta troncata. Allowlist MIME
      e magic bytes, Pillow/ffprobe; immagini max 15 MB/40 MP e video max
      100 MB/300 secondi.
- [x] **Originali e varianti separate** in MinIO con stato/errori di
      processing e metadati nel DB. Le API restituiscono URL presigned a
      breve durata tramite `MINIO_PUBLIC_ENDPOINT`; i task partono solo
      dopo commit e sono idempotenti/ritentabili.
- [x] **Lifecycle e orfani**: configurazione giornaliera MinIO per
      multipart incompleti/temporanei dopo un giorno e pulizia notturna
      DB-aware dei soli oggetti non referenziati da oltre 24 ore. Nessuna
      scadenza viene applicata a media ancora collegati.
- [x] **CDN valutata e rinviata**: rivalutare quando egress supera
      100 GB/mese oppure p95 di caricamento media supera 500 ms per due
      settimane consecutive.

La pipeline FFmpeg è verificata localmente su video sintetico con controllo
di codec/risoluzione, thumbnail, cinque frame e originali invariati. La
verifica dell'intero stack Docker resta dipendente dall'accesso al daemon
Docker dell'host.

## 7. Esportazioni

- [x] Implementare la **generazione reale del pacchetto zip con
      manifest**: JSON/CSV, provenienza, hash, esclusioni e sole varianti
      display/thumbnail; gli originali non entrano mai nel pacchetto.
- [x] Eseguire gli export sulla **coda Celery dedicata `exports`**, con
      worker a concorrenza 1 separato da `scraping`/`media`/`ai`.
- [x] Implementare lo **storage temporaneo** dei pacchetti generati su
      MinIO con URL firmati a scadenza.
- [x] Implementare il **job periodico di pulizia** dei job di export
      scaduti (`export_jobs.expires_at`), sia il record DB sia il file
      su MinIO.
- [x] Definire limiti su **dimensione massima/numero di record per
      export**: 1.000 record e 2 GiB non compressi, configurabili.

## 8. Sicurezza / GDPR

- [ ] Ottenere **validazione legale specialistica** sullo scraping di
      dati personali (numeri di telefono, contenuti media) da fonti
      terze, per ciascuna fonte configurata dall'operatore con il motore
      generico (richiamo a `docs/SICUREZZA.md` §7 e al §21 del PDF di
      progetto).
- [x] Definire e rendere **configurabile la retention** per ogni
      categoria di dato (annunci, media, log, audit log) — collegata al
      punto 2 (retention policy DB).
- [x] Definire e implementare le **procedure di cancellazione dati** su
      richiesta (diritto all'oblio), incluso l'impatto sulla
      deduplicazione (cosa succede a un `record` se uno degli annunci
      collegati va cancellato).
- [x] Definire policy di **accesso e minimizzazione visualizzazione** del
      numero di telefono in chiaro (chi può vederlo per esteso vs. solo
      mascherato, quali azioni vengono loggate in `audit_log` quando il
      dato in chiaro viene effettivamente decifrato e mostrato).
- [x] Eseguire una **security review interna** prima del go-live
      (vedi anche skill `security-review` disponibile nel repo per una
      prima passata automatizzata, non sostitutiva di un audit esterno).
      Review e remediation documentate in
      `docs/SECURITY_REVIEW_2026-09-02.md`; il **penetration test esterno**
      rimane un gate obbligatorio e non è dichiarato come eseguito.
- [ ] Verificare conformità nell'invio di dati a provider LLM esterni
      (sezione 5) rispetto ai requisiti GDPR (minimizzazione, eventuale
      DPA con il provider).

## 9. Observability

- [x] Costruire le **dashboard Grafana specifiche** del progetto:
      sono provisionate (a) salute API (latenze, error rate,
      richieste/minuto), (b) stato worker Celery per coda (lunghezza
      coda, task falliti, tempo di esecuzione), (c) stato scraping per
      fonte (successo/fallimento run, nuovi annunci trovati).
- [x] Implementare l'**endpoint `/metrics`** lato API tramite
      `prometheus-fastapi-instrumentator` e collector applicativo DB-backed.
- [x] Configurare l'**invio dei log applicativi a Loki** tramite Grafana Alloy
      e discovery filtrata dei container Docker del progetto.
- [x] Definire **alerting** (Grafana Alerting o Alertmanager) su almeno:
      API down, coda Celery bloccata/troppo lunga, run di scraping
      falliti ripetutamente per una fonte, spazio disco MinIO/Postgres.
- [x] Aggiungere **postgres_exporter**, Redis exporter, Celery exporter e
      node exporter per i volumi, tutti come target interni di Prometheus.

## 10. Deploy

- [ ] Definire e provisionare l'**ambiente di staging** e quello di
      **produzione** (hosting: VPS dedicato, cloud provider — decisione
      da prendere con il cliente).
- [ ] Configurare **dominio e DNS** per l'ambiente pubblico.
- [ ] Configurare **TLS** (es. Let's Encrypt/reverse proxy con
      certificati automatici, o terminazione TLS a livello di load
      balancer/CDN a monte di `nginx`) — nel setup attuale nginx espone
      solo la porta 80 in chiaro.
- [ ] Configurare **backup automatici** end-to-end (Postgres + MinIO) con
      test periodico di ripristino (collegato al punto 2).
- [ ] Implementare **secrets management** in produzione (oggi solo file
      `.env` locale): valutare un vault/secrets manager del provider
      cloud scelto, evitare segreti in chiaro sulle macchine di deploy.
- [ ] Restringere l'esposizione pubblica di **MinIO console (9001)**,
      **Grafana (3000)** e **Prometheus (9090)**: nel `docker-compose.yml`
      attuale sono pubblicate per comodità di sviluppo, in produzione
      vanno messe dietro VPN/autenticazione o rimosse da `ports:`.
      pubblico.
- [ ] Configurare **pipeline di deploy** (CD) — oggi la CI
      (`.github/workflows/ci.yml`) fa solo lint/test/build immagini,
      senza push né deploy: aggiungere step di push su registry e deploy
      automatico/manuale verso staging/produzione.
- [ ] Definire strategia di **scaling dei worker Celery** per coda in
      base al carico reale (numero di repliche per `worker-scraper` /
      `worker-media` / `worker-ai`).
- [ ] Definire piano di **disaster recovery** (RPO/RTO) concordato con il
      cliente.

## 11. Note di compromesso su questa consegna

`frontend/` e `backend/` sono stati completati e la coerenza con
`docker-compose.yml`/`.env.example` è stata verificata a posteriori:
- `command` dei servizi Celery corretto a `-A app.workers.celery_app`
  (il modulo reale, non `app.worker`).
- `.env.example` allineato ai nomi effettivi letti da `backend/app/config.py`
  (`DATABASE_URL` in schema `asyncpg`, aggiunta `DATABASE_URL_SYNC` per i
  worker, `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY`/`MINIO_SECURE`,
  `JWT_ACCESS_TTL_MINUTES`/`JWT_REFRESH_TTL_DAYS`, singola `JWT_SECRET_KEY`).
- `docker-compose.yml` passa `VITE_API_URL` come build arg al servizio
  `frontend` (necessario perché Vite lo "bake-a" nel bundle statico a
  build-time, non a runtime), puntato al reverse proxy pubblico e non alla
  porta interna 8000 dell'api.
- Aggiunto `.gitignore` root mancante.
- `.github/workflows/ci.yml` corretto; `uv.lock` è ora generato e va usato
  per installazioni backend riproducibili. Env var di test allineate, rimosso lo step di build
  Docker per `nginx` (nel compose usa l'immagine ufficiale con config
  montata, non un Dockerfile dedicato).
- Contratto API backend↔frontend riconciliato con un passaggio dedicato
  (endpoint `dashboard`, `records/*`, `sources/*`, `exports/*`, `admin/*`
  mancanti sono stati implementati nel backend per soddisfare esattamente
  le chiamate in `frontend/src/api/*.ts`) e poi verificato ulteriormente a
  mano: sono stati trovati e corretti altri due mismatch sfuggiti al primo
  giro, entrambi bloccanti per l'uso base dell'app:
  - `POST /auth/login`/`login-2fa`/`GET /auth/me` rispondevano con
    `requires_2fa`/`login_ticket` e senza l'oggetto `user`, mentre il
    frontend (`frontend/src/api/auth.ts`) si aspetta `status`/`mfa_token`
    e un `user` con `id/email/name/role/mfaEnabled/status` — schema e
    router riscritti (`backend/app/schemas/auth.py:UserPublic`,
    `backend/app/api/v1/auth.py`). `user.name`/`user.status` sono derivati
    (email/`is_active`), nessuna colonna dedicata nel modello `User`.
  - `GET /sources` rispondeva con la forma "grezza" del modello (`slug`,
    `base_url`, `priority`, snake_case) invece di `code`/`country`/
    `lastRunAt`/`itemsLast24h`/`errorRate` in camelCase attesi dal
    frontend — corretto in `backend/app/schemas/sources.py` (ora
    `CamelModel`) e `backend/app/api/v1/sources.py` (calcolo aggregato da
    `scrape_runs`, N+1 accettato per il volume di fonti atteso). `country`
    resta un placeholder fisso `"N/D"`.
  Entrambe le correzioni sono state verificate con `python -m py_compile`,
  import completo di `app.main` (41 route registrate) e l'intera suite
  pytest (54/54 passati).

## 12. Verifica end-to-end reale (`docker compose up --build`) e bug trovati

A differenza delle verifiche precedenti (solo statiche: compilazione, test
unitari), in questa sessione lo stack è stato **davvero avviato** con
Docker Desktop e testato dal vivo. Sono emersi e sono stati corretti
diversi bug che nessuna verifica statica poteva intercettare:

- **`npm install` falliva** (`ERESOLVE`): `eslint-plugin-react-hooks@^4.6.2`
  non supporta ESLint 9. Aggiornato a `^5.0.0` in `frontend/package.json`.
- **`npm run build` falliva** (errori TypeScript): mancava
  `frontend/src/vite-env.d.ts` (necessario per i tipi di `import.meta.env`),
  `tsconfig.node.json` non aveva `"types": ["node"]`/`@types/node` come
  dipendenza (necessario per `node:url` in `vite.config.ts`), e un import
  `Badge` inutilizzato in `RecordOccurrencesTab.tsx`. Tutti corretti;
  `npm run build` e `npm run lint` sono ora puliti (0 errori).
- **`eslint.config.js` segnalava decine di falsi `no-undef`** su tipi DOM
  ambientali TypeScript (`HTMLDivElement`, `RequestInit`, ecc., che non
  sono globals runtime): `no-undef` disabilitato per i file TS/TSX (tsc
  già copre questo caso con piena informazione di tipo).
- **`pip install -e .` falliva nel Dockerfile del backend**: `pyproject.toml`
  dichiarava `readme = "README.md"` ma quel file non esiste in
  `backend/`. Rimosso il campo (non obbligatorio).
- **Le migrazioni Alembic fallivano** con `DuplicateObjectError: type
  "user_role" already exists` al primo `alembic upgrade head` su un DB
  vuoto: gli enum Postgres venivano creati esplicitamente
  (`enum_type.create(bind, checkfirst=True)`) E ricreati implicitamente
  da `op.create_table` (l'oggetto `postgresql.ENUM` senza
  `create_type=False` spara un secondo `CREATE TYPE` come effetto
  collaterale della creazione della tabella). Corretto aggiungendo
  `create_type=False` a tutti gli 8 enum in
  `backend/migrations/versions/20260827120000_initial_schema.py`.
  Verificato: `docker compose exec api alembic upgrade head` crea ora
  tutte le 12 tabelle correttamente su un Postgres reale.
- **Nessun modo di creare il primo utente Admin**: `POST /admin/users`
  richiede già un Admin autenticato con 2FA attiva (corretto come modello
  di sicurezza, ma è un problema di bootstrap). Aggiunto
  `backend/app/scripts/create_admin.py`, script one-shot da eseguire con
  `docker compose exec api python -m app.scripts.create_admin --email
  ... --password ...`, documentato in `README.md` e `docs/SVILUPPO.md`.
- **`GET /api/v1/sources` e `GET /api/v1/exports` rispondevano 307**
  (redirect a `.../sources/`, `.../exports/`) quando chiamati senza
  slash finale, come fa il frontend: FastAPI genera un redirect quando la
  route è registrata come `@router.get("/")` sotto un prefisso. Corretto
  cambiando la route in `@router.get("")` in `sources.py`, `exports.py`
  (get e post) e, per coerenza, `search.py`.
- `docs/SVILUPPO.md` conteneva istruzioni non allineate al codice reale
  (nomi metodi scraper inventati, campi `sources` inesistenti come
  `rate_limit_config`/`robots_txt_checked_at`, endpoint `POST
  /sources/{id}/runs` mai esistito, variabili JWT vecchie): corretto per
  riflettere l'interfaccia `Scraper` reale (`discover`/`scrape_ad`/
  `download_media`/`normalize`) e gli endpoint effettivamente presenti.
- **`loki` in crash-loop**: `infra/loki/loki-config.yml` aveva
  `compactor.retention_enabled: true` senza `delete_request_store`,
  richiesto dalle versioni recenti di Loki quando la retention è attiva.
  Aggiunto `delete_request_store: filesystem` (coerente con lo storage
  filesystem locale già configurato). Verificato: il container resta
  stabile ("Loki started") invece di riavviarsi in loop.

**Verificato con successo dal vivo** (Docker Desktop, `docker compose up
--build` con tutti i 13 servizi): build di tutte le 6 immagini custom,
avvio di tutti i container, `alembic upgrade head` con creazione delle 12
tabelle, bootstrap del primo Admin, `POST /api/v1/auth/login` con risposta
esatta attesa dal frontend (`status`/`access_token`/`refresh_token`/
`user`), `GET /auth/me`, `GET /sources`, `GET /sources/summary`, `GET
/exports`, `GET /dashboard/kpis`, `GET /admin/users` tutti raggiungibili
tramite il reverse proxy nginx su `http://localhost/` con risposta 200 e
forma corretta. Il bundle frontend è stato verificato contenere l'URL API
corretto (`http://localhost/api/v1`, iniettato da `VITE_API_URL` come
build-arg).

**Non ancora verificato**: navigazione manuale dell'interfaccia in un
browser reale (solo l'API è stata esercitata via `curl`), flusso 2FA
completo (setup QR code + verifica + login con TOTP), scraper reali,
generazione export reale, dashboard Grafana.

Resta da fare un giro di verifica **eseguendo davvero** `docker compose up
--build` end-to-end (non ancora testato in questo ambiente per assenza di
Docker), e generare un `uv.lock`/`package-lock.json` reali eseguendo
`uv sync` e `npm install` in locale.

## 13. Localizzazione italiana

- [x] Catalogo i18n frontend con lingua fissa italiana e fallback italiano.
- [x] Navigazione, pagine operative, form, errori, stati e testi accessibili in italiano.
- [x] Formattazione `it-IT` e orari applicativi in `Europe/Rome`.
- [x] Messaggi di validazione API italiani senza modifica del contratto JSON.
- [x] Prompt storici `summary-v1` preservati e nuovi riepiloghi su `summary-v2-it`.
- [x] Migrazione idempotente della configurazione AI, senza rigenerazione dello storico.
- [x] Controllo automatico delle nuove stringhe UI inglesi (`npm run check:i18n`).

Gli identificatori tecnici, le route, i campi JSON, gli enum e lo schema dati
restano in inglese per compatibilità. Rimangono invariati anche contenuti
acquisiti, campi custom, marchi, provider e modelli AI.

## 14. Evoluzione fonti, acquisizione e integrazioni

- [x] Media sempre visibili senza blur, con badge di classificazione esplicito.
- [x] Paese ISO 3166-1 opzionale per fonte, con bandiera Unicode e trasferimento completo.
- [x] Pianificazione automatica integrata nella configurazione della fonte.
- [x] Export record singolo, selezionato, filtrato e completo oltre 1.000 risultati.
- [x] Sanitizzazione selettiva di titolo, descrizione e campi marcati tramite Gemma locale.
- [x] Pubblicazione idempotente a batch configurabile con commit del resto finale.
- [x] Webhook multipli per tutte o specifiche fonti, HMAC, retry e politiche telefono.
- [x] Paginazione globale fino alla fine, con limiti opzionali attivati tramite checkbox.
- [x] Feed proxy HTTPS periodici con header cifrati e riconciliazione del pool.
- [x] Pagina listing persistita e usata come primo criterio della selezione canonica.
- [x] Dettaglio completo e versioni disponibili nella tab Occorrenze.
