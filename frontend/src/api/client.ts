// Thin fetch wrapper shared by every api/* module.
//
// Responsibilities:
//  - Prefix requests with VITE_API_URL.
//  - Attach the JWT access token from storage.
//  - Transparently refresh the access token once on a 401 and retry the
//    original request, so callers (hooks/pages) never have to think about it.
//  - Normalize error responses into a typed ApiError.

// Same-origin is the safe production default: nginx exposes both the SPA and
// `/api/v1`, so the bundle also works through the IPv4 diagnostic URL without
// baking a second hostname into fetch requests. Vite development may still
// override this with VITE_API_URL.
const API_BASE_URL = import.meta.env.VITE_API_URL ?? "/api/v1";

const ACCESS_TOKEN_KEY = "lavoro_esterno_access_token";
const REFRESH_TOKEN_KEY = "lavoro_esterno_refresh_token";

export const tokenStorage = {
  getAccessToken: () => localStorage.getItem(ACCESS_TOKEN_KEY),
  getRefreshToken: () => localStorage.getItem(REFRESH_TOKEN_KEY),
  setTokens: (accessToken: string, refreshToken: string) => {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  },
  clear: () => {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  },
};

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, message: string, body?: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  // Skip attaching a token / triggering refresh (used by login & refresh calls themselves).
  skipAuth?: boolean;
}

// A single in-flight refresh promise, shared by every request that races into
// a 401 at the same time, so we don't fire N parallel refresh calls.
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = tokenStorage.getRefreshToken();
  if (!refreshToken) return null;

  if (!refreshPromise) {
    refreshPromise = fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
      .then(async (res) => {
        if (!res.ok) return null;
        const data = await res.json();
        tokenStorage.setTokens(data.access_token, data.refresh_token);
        return data.access_token as string;
      })
      .catch(() => null)
      .finally(() => {
        refreshPromise = null;
      });
  }

  return refreshPromise;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { skipAuth, body, headers, ...rest } = options;

  const doFetch = async (): Promise<Response> => {
    const finalHeaders: HeadersInit = {
      "Content-Type": "application/json",
      ...headers,
    };
    if (!skipAuth) {
      const token = tokenStorage.getAccessToken();
      if (token) (finalHeaders as Record<string, string>).Authorization = `Bearer ${token}`;
    }
    return fetch(`${API_BASE_URL}${path}`, {
      ...rest,
      headers: finalHeaders,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  };

  let res = await doFetch();

  // Attempt exactly one silent refresh-and-retry before surfacing the 401 to the caller.
  if (res.status === 401 && !skipAuth) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      res = await doFetch();
    } else {
      tokenStorage.clear();
      // Let AuthContext's consumers react by reloading into the login route.
      window.dispatchEvent(new Event("lavoro-esterno:session-expired"));
    }
  }

  if (!res.ok) {
    let parsedBody: unknown;
    try {
      parsedBody = await res.json();
    } catch {
      parsedBody = undefined;
    }

    // `detail` is usually a plain string, but some endpoints (rate-limit
    // lockouts, mandatory-2FA enforcement) return a structured object like
    // `{ error_code, message, retry_after_seconds? }` — extract a readable
    // string either way instead of stringifying the whole object.
    const detail = (parsedBody as { detail?: unknown } | undefined)?.detail;
    const errorCode =
      detail && typeof detail === "object" ? (detail as { error_code?: string }).error_code : undefined;
    const message =
      (typeof detail === "string" ? detail : undefined) ??
      (detail && typeof detail === "object" ? (detail as { message?: string }).message : undefined) ??
      (parsedBody as { message?: string } | undefined)?.message ??
      res.statusText;

    if (errorCode === "mfa_setup_required") {
      window.dispatchEvent(new Event("lavoro-esterno:mfa-setup-required"));
    }

    throw new ApiError(res.status, message, parsedBody);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export { API_BASE_URL };
