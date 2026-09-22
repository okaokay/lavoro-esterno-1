/** Catalogo italiano canonico usato dall'interfaccia. */
export const it = {
  translation: {
    app: { name: "Lavoro Esterno", tagline: "Gestione dati aziendali" },
    nav: {
      dashboard: "Panoramica", records: "Record", sources: "Fonti", exports: "Esportazioni",
      settings: "Impostazioni", admin: "Amministrazione", account: "Account", logout: "Esci",
      overview: "Riepilogo", occurrences: "Occorrenze", media: "Media", aiSummary: "Riepilogo AI",
      history: "Cronologia", proxies: "Proxy",
    },
    common: {
      loading: "Caricamento…", save: "Salva", saving: "Salvataggio…", cancel: "Annulla",
      close: "Chiudi", delete: "Elimina", edit: "Modifica", create: "Crea", retry: "Riprova",
      refresh: "Aggiorna", confirm: "Conferma", enabled: "Abilitato", disabled: "Disabilitato",
      active: "Attivo", inactive: "Inattivo", yes: "Sì", no: "No", all: "Tutti",
      none: "Nessuno", actions: "Azioni", status: "Stato", name: "Nome", type: "Tipo",
      date: "Data", details: "Dettagli", source: "Fonte", unknown: "Sconosciuto",
      noData: "Nessun dato disponibile.", loadError: "Impossibile caricare i dati.",
      unexpectedError: "Si è verificato un errore imprevisto.", search: "Cerca", clear: "Azzera",
      previous: "Precedente", next: "Successiva", page: "Pagina", of: "di",
    },
    header: {
      systemStatus: "Stato del sistema", notifications: "Notifiche", markAllRead: "Segna tutte come lette",
      noNotifications: "Nessun avviso operativo.", notificationsError: "Impossibile caricare le notifiche.",
      lightMode: "Passa al tema chiaro", darkMode: "Passa al tema scuro", breadcrumb: "Percorso di navigazione",
    },
    status: {
      pending: "In attesa", processing: "In elaborazione", running: "In esecuzione", completed: "Completato",
      failed: "Non riuscito", cancelled: "Annullato", ready: "Pronto", safe: "Sicuro",
      explicit: "Esplicito", unclassified: "Non classificato", needsReview: "Da revisionare",
      healthy: "Operativo", degraded: "Degradato", unavailable: "Non disponibile", offline: "Fuori linea",
      waiting: "In attesa", paused: "In pausa", scheduled: "Pianificato", manual: "Manuale",
      suspended: "Sospeso", invited: "Invitato", draft: "Bozza", confirmed: "Confermato",
    },
    errors: {
      boundaryTitle: "Qualcosa è andato storto", boundaryText: "Ricarica la pagina oppure riprova tra poco.",
      validation: "Controlla i campi evidenziati.", unauthorized: "Devi effettuare l’accesso.",
      forbidden: "Non disponi dei permessi necessari.", notFound: "Risorsa non trovata.",
    },
  },
} as const;

export type TranslationResources = typeof it;
