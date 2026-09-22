import { ApiError } from "@/api/client";

// Central place mapping an error (ApiError from the backend, or a raw
// network/rendering failure) to what a page should actually show the user.
// Before this existed, every page hand-rolled its own flat error string —
// same generic wording for a 404, a 500, and "the network is down", with no
// way to offer a "Retry" action or read `retry_after_seconds` off a 429.

export interface ErrorPresentation {
  title: string;
  description: string;
  // Whether showing a "Retry" affordance makes sense (a 403 permission
  // error retrying with the same request won't ever succeed; a 500/network
  // blip might).
  retryable: boolean;
  // Present only for rate-limit lockouts (429, or 403 login lockouts that
  // reuse the same shape) — seconds until the caller may try again.
  retryAfterSeconds?: number;
}

interface StructuredDetail {
  error_code?: string;
  message?: string;
  retry_after_seconds?: number;
}

function structuredDetail(body: unknown): StructuredDetail | undefined {
  if (!body || typeof body !== "object") return undefined;
  const detail = (body as { detail?: unknown }).detail;
  if (!detail || typeof detail !== "object") return undefined;
  return detail as StructuredDetail;
}

export function describeError(error: unknown): ErrorPresentation {
  if (error instanceof ApiError) {
    const detail = structuredDetail(error.body);

    if (error.status === 429 || detail?.error_code === "too_many_attempts") {
      return {
        title: "Troppi tentativi",
        description: detail?.message ?? error.message,
        retryable: false,
        retryAfterSeconds: detail?.retry_after_seconds,
      };
    }
    if (error.status === 403) {
      return {
        title: "Accesso negato",
        description:
          detail?.message ?? error.message ?? "Non disponi dei permessi necessari.",
        retryable: false,
      };
    }
    if (error.status === 404) {
      return {
        title: "Risorsa non trovata",
        description: error.message || "La risorsa richiesta non esiste oppure è stata rimossa.",
        retryable: false,
      };
    }
    if (error.status >= 500) {
      return {
        title: "Errore del server",
        description: "Si è verificato un errore sul server. Riprova tra poco.",
        retryable: true,
      };
    }
    // 400/401/409/422/... — no dedicated case, but still a real message
    // from the API worth showing verbatim rather than a generic fallback.
    return { title: "Richiesta non riuscita", description: error.message || "Riprova.", retryable: true };
  }

  // fetch() throws a plain TypeError (not an ApiError) when the network is
  // unreachable entirely — CORS failure, DNS failure, server not running.
  if (error instanceof TypeError) {
    return {
      title: "Errore di rete",
      description: "Impossibile raggiungere il server. Controlla la connessione e riprova.",
      retryable: true,
    };
  }

  return {
    title: "Errore imprevisto",
    description: error instanceof Error ? error.message : "Si è verificato un errore.",
    retryable: true,
  };
}
