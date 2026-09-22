import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import Icon from "@/components/ui/Icon";
import { describeError } from "@/lib/errors";
import { useCountdown } from "@/hooks/useCountdown";

// Local shape for the banner state: either a plain error message, or a
// rate-limit lockout with a live countdown (see describeError in
// src/lib/errors.ts, which reads `retry_after_seconds` off the 429/403 body
// the backend returns for /auth/login, /auth/login-2fa, /auth/verify-2fa).
interface FormError {
  title: string;
  description: string;
  retryAfterSeconds?: number;
}

// Replicates desing/login_lavoro_esterno/code.html: a centered card with a
// header, form body and a "Restricted Access" footer. The form has two
// steps: email+password, then (if the backend reports mfa_required) a
// 6-digit code step — the mfaToken from step 1 is threaded through state.
export default function LoginPage() {
  const { login, verifyTwoFactor, user, requiresTwoFactorSetup } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [step, setStep] = useState<"credentials" | "mfa">("credentials");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [useBackupCode, setUseBackupCode] = useState(false);
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [error, setError] = useState<FormError | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const lockoutRemaining = useCountdown(error?.retryAfterSeconds);
  const isLockedOut = Boolean(lockoutRemaining && lockoutRemaining > 0);
  // Shown once, blocking, when the last backup code was just consumed and
  // the backend auto-regenerated a fresh set: never let these be lost
  // silently, they're the user's only account-recovery fallback.
  const [newBackupCodes, setNewBackupCodes] = useState<string[] | null>(null);
  const [pendingRedirect, setPendingRedirect] = useState<string | null>(null);

  // If a session already exists (e.g. user navigated back to /login), skip the form.
  if (user) {
    const redirectTo = requiresTwoFactorSetup
      ? "/2fa-setup"
      : ((location.state as { from?: Location })?.from?.pathname ?? "/dashboard");
    return <Navigate to={redirectTo} replace />;
  }

  const handleCredentialsSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await login(email, password);
      if (result.status === "mfa_required") {
        setMfaToken(result.mfaToken);
        setStep("mfa");
      } else if (result.status === "mfa_setup_required") {
        navigate("/2fa-setup", { replace: true });
      } else {
        navigate("/dashboard", { replace: true });
      }
    } catch (err) {
      const { title, description, retryAfterSeconds } = describeError(err);
      setError({ title, description, retryAfterSeconds });
    } finally {
      setSubmitting(false);
    }
  };

  const handleMfaSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!mfaToken) return;
    setError(null);
    setSubmitting(true);
    try {
      const regeneratedCodes = await verifyTwoFactor(mfaToken, code);
      if (regeneratedCodes && regeneratedCodes.length > 0) {
        setNewBackupCodes(regeneratedCodes);
        setPendingRedirect("/dashboard");
      } else {
        navigate("/dashboard", { replace: true });
      }
    } catch (err) {
      const { title, description, retryAfterSeconds } = describeError(err);
      setError({ title, description, retryAfterSeconds });
    } finally {
      setSubmitting(false);
    }
  };

  if (newBackupCodes) {
    return (
      <div className="bg-background text-on-background min-h-screen flex items-center justify-center p-margin-page">
        <div className="w-full max-w-[420px] bg-surface-container-lowest border border-border rounded-lg shadow-[0_4px_24px_rgba(0,0,0,0.04)] overflow-hidden flex flex-col p-8 gap-4">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-warning">warning</span>
            <h2 className="text-headline-sm text-on-surface">Nuovi codici di recupero generati</h2>
          </div>
          <p className="text-body-md text-on-surface-variant">
            Hai appena utilizzato l’ultimo codice di recupero. È stato generato automaticamente un nuovo insieme: salvalo ora, perché non verrà mostrato di nuovo.
          </p>
          <div className="grid grid-cols-2 gap-2 font-mono text-mono-data bg-surface border border-outline-variant rounded p-3">
            {newBackupCodes.map((c) => (
              <span key={c}>{c}</span>
            ))}
          </div>
          <button
            type="button"
            onClick={() => navigate(pendingRedirect ?? "/dashboard", { replace: true })}
            className="w-full py-2.5 px-4 rounded shadow-sm text-label-sm text-on-primary bg-primary hover:bg-primary-container transition-colors"
          >
            Ho salvato i nuovi codici di recupero
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-background text-on-background min-h-screen flex items-center justify-center p-margin-page">
      <div className="w-full max-w-[420px] bg-surface-container-lowest border border-border rounded-lg shadow-[0_4px_24px_rgba(0,0,0,0.04)] overflow-hidden flex flex-col">
        <div className="p-8 pb-6 text-center border-b border-border bg-surface-bright">
          <h1 className="text-headline-lg text-primary tracking-tight mb-2">Lavoro Esterno</h1>
          <p className="text-label-sm text-on-surface-variant uppercase tracking-widest">Gestione dati aziendali</p>
        </div>

        <div className="p-8 pt-6 flex-1 flex flex-col justify-center">
          {error && (
            <div className="mb-4 px-3 py-2 rounded bg-error-container/40 text-error text-body-md">
              <p className="font-semibold">{error.title}</p>
              <p>{error.description}</p>
              {isLockedOut && <p className="mt-1 font-mono text-mono-data">Riprova tra {lockoutRemaining}s</p>}
            </div>
          )}

          {step === "credentials" ? (
            <form className="space-y-5" onSubmit={handleCredentialsSubmit}>
              <div className="space-y-1.5">
                <label className="block text-label-sm text-on-surface" htmlFor="email">
                  Email / Nome utente
                </label>
                <div className="relative">
                  <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline text-[18px]">
                    person
                  </span>
                  <input
                    id="email"
                    name="email"
                    type="text"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="user@lavoro.internal"
                    className="block w-full pl-9 pr-3 py-2 border border-outline-variant rounded bg-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container font-mono text-mono-data text-on-surface placeholder-outline-variant transition-colors outline-none"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="block text-label-sm text-on-surface" htmlFor="password">
                  Password
                </label>
                <div className="relative">
                  <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline text-[18px]">
                    lock
                  </span>
                  <input
                    id="password"
                    name="password"
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="block w-full pl-9 pr-3 py-2 border border-outline-variant rounded bg-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container font-mono text-mono-data text-on-surface placeholder-outline-variant transition-colors outline-none"
                  />
                </div>
              </div>

              <div className="pt-4">
                <button
                  type="submit"
                  disabled={submitting || isLockedOut}
                  className="w-full flex justify-center py-2.5 px-4 rounded shadow-sm text-label-sm text-on-primary bg-primary hover:bg-primary-container focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary transition-colors disabled:opacity-60"
                >
                  {isLockedOut ? `Riprova tra ${lockoutRemaining}s` : submitting ? "Accesso…" : "Accedi"}
                </button>
              </div>
            </form>
          ) : (
            <form className="space-y-5" onSubmit={handleMfaSubmit}>
              <div className="text-center space-y-1">
                <Icon name="verified_user" className="text-primary" size={28} />
                <p className="text-body-md text-on-surface-variant">
                  {useBackupCode
                    ? "Inserisci uno dei codici di recupero di 10 caratteri."
                    : "Inserisci il codice a 6 cifre dell’app di autenticazione."}
                </p>
              </div>
              <div className="space-y-1.5">
                <label className="block text-label-sm text-on-surface" htmlFor="mfa-code">
                  Codice di verifica
                </label>
                {useBackupCode ? (
                  <input
                    id="mfa-code"
                    name="code"
                    type="text"
                    maxLength={12}
                    required
                    autoFocus
                    value={code}
                    onChange={(e) => setCode(e.target.value.toUpperCase().slice(0, 12))}
                    placeholder="A1B2C3D4E5"
                    className="block w-full text-center tracking-[0.2em] py-2 px-3 border border-outline-variant rounded bg-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container font-mono text-headline-sm text-on-surface placeholder-outline-variant transition-colors outline-none"
                  />
                ) : (
                  <input
                    id="mfa-code"
                    name="code"
                    type="text"
                    inputMode="numeric"
                    pattern="\d{6}"
                    maxLength={6}
                    required
                    autoFocus
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                    placeholder="000000"
                    className="block w-full text-center tracking-[0.5em] py-2 px-3 border border-outline-variant rounded bg-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container font-mono text-headline-sm text-on-surface placeholder-outline-variant transition-colors outline-none"
                  />
                )}
              </div>
              <div className="pt-2">
                <button
                  type="submit"
                  disabled={
                    submitting || isLockedOut || (useBackupCode ? code.length < 6 : code.length !== 6)
                  }
                  className="w-full flex justify-center py-2.5 px-4 rounded shadow-sm text-label-sm text-on-primary bg-primary hover:bg-primary-container focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary transition-colors disabled:opacity-60"
                >
                  {isLockedOut ? `Riprova tra ${lockoutRemaining}s` : submitting ? "Verifica…" : "Verifica"}
                </button>
              </div>
              <button
                type="button"
                onClick={() => {
                  setUseBackupCode((v) => !v);
                  setCode("");
                }}
                className="w-full text-center text-label-sm text-on-surface-variant hover:text-primary transition-colors"
              >
                {useBackupCode ? "Usa il codice dell’app" : "Usa un codice di recupero"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setStep("credentials");
                  setCode("");
                  setUseBackupCode(false);
                }}
                className="w-full text-center text-label-sm text-on-surface-variant hover:text-primary transition-colors"
              >
                Torna all’accesso
              </button>
            </form>
          )}
        </div>

        <div className="px-8 py-4 bg-surface-container-low border-t border-border flex items-center justify-center gap-2">
          <span className="material-symbols-outlined text-warning" style={{ fontSize: 16 }}>
            warning
          </span>
          <p className="text-label-sm text-on-surface-variant">Accesso riservato / Sistema interno</p>
        </div>
      </div>
    </div>
  );
}
