import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import * as authApi from "@/api/auth";
import Icon from "@/components/ui/Icon";
import { describeError } from "@/lib/errors";
import { useCountdown } from "@/hooks/useCountdown";

interface FormError {
  title: string;
  description: string;
  retryAfterSeconds?: number;
}

// Mandatory 2FA enrollment screen: shown whenever an Admin/Operator account
// hasn't activated TOTP yet (ProtectedRoute redirects here for any other
// route, mirroring the backend's own enforcement in
// app/security/deps.py:get_current_user). No mockup exists for this screen
// (it's a new, previously-missing flow) — styled consistently with
// LoginPage.tsx using the same Tailwind design tokens, not a pixel-perfect
// replica of anything in desing/.
export default function TwoFactorSetupPage() {
  const { completeTwoFactorSetup, logout } = useAuth();
  const navigate = useNavigate();

  const [loadingSetup, setLoadingSetup] = useState(true);
  const [qrCodeBase64, setQrCodeBase64] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [savedCodesAck, setSavedCodesAck] = useState(false);
  const [code, setCode] = useState("");
  const [error, setError] = useState<FormError | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const lockoutRemaining = useCountdown(error?.retryAfterSeconds);
  const isLockedOut = Boolean(lockoutRemaining && lockoutRemaining > 0);

  useEffect(() => {
    let cancelled = false;
    authApi
      .setupTwoFactor()
      .then((setup) => {
        if (cancelled) return;
        setQrCodeBase64(setup.qrCodeBase64);
        setSecret(setup.secret);
        setBackupCodes(setup.backupCodes);
      })
      .catch((err) => {
        const { title, description, retryAfterSeconds } = describeError(err);
        setError({ title, description, retryAfterSeconds });
      })
      .finally(() => setLoadingSetup(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const handleVerify = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await completeTwoFactorSetup(code);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      const { title, description, retryAfterSeconds } = describeError(err);
      setError({ title, description, retryAfterSeconds });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bg-background text-on-background min-h-screen flex items-center justify-center p-margin-page">
      <div className="w-full max-w-[480px] bg-surface-container-lowest border border-border rounded-lg shadow-[0_4px_24px_rgba(0,0,0,0.04)] overflow-hidden flex flex-col">
        <div className="p-8 pb-6 text-center border-b border-border bg-surface-bright">
          <Icon name="verified_user" className="text-primary mb-2" size={28} />
          <h1 className="text-headline-lg text-primary tracking-tight mb-2">Configurazione a due fattori obbligatoria</h1>
          <p className="text-body-md text-on-surface-variant">
            Il tuo ruolo richiede l’autenticazione a due fattori prima di poter continuare.
          </p>
        </div>

        <div className="p-8 pt-6 flex-1 flex flex-col justify-center gap-5">
          {error && (
            <div className="px-3 py-2 rounded bg-error-container/40 text-error text-body-md">
              <p className="font-semibold">{error.title}</p>
              <p>{error.description}</p>
              {isLockedOut && <p className="mt-1 font-mono text-mono-data">Riprova tra {lockoutRemaining}s</p>}
            </div>
          )}

          {loadingSetup ? (
            <p className="text-center text-body-md text-on-surface-variant">Preparazione configurazione…</p>
          ) : !savedCodesAck ? (
            <>
              <div className="flex flex-col items-center gap-3">
                {qrCodeBase64 && (
                  <img
                    src={`data:image/png;base64,${qrCodeBase64}`}
                    alt="Codice QR TOTP"
                    className="w-40 h-40 border border-outline-variant rounded"
                  />
                )}
                <p className="text-label-sm text-on-surface-variant text-center">
                  Scansiona con Google Authenticator o Microsoft Authenticator, oppure inserisci manualmente questa chiave:
                </p>
                <code className="font-mono text-mono-data text-on-surface bg-surface px-2 py-1 rounded border border-outline-variant">
                  {secret}
                </code>
              </div>

              <div className="space-y-2">
                <p className="text-label-sm text-on-surface">
                  Salva ora questi codici di recupero: ciascuno può essere usato una sola volta e non verrà mostrato di nuovo.
                </p>
                <div className="grid grid-cols-2 gap-2 font-mono text-mono-data bg-surface border border-outline-variant rounded p-3">
                  {backupCodes.map((c) => (
                    <span key={c}>{c}</span>
                  ))}
                </div>
              </div>

              <button
                type="button"
                onClick={() => setSavedCodesAck(true)}
                className="w-full py-2.5 px-4 rounded shadow-sm text-label-sm text-on-primary bg-primary hover:bg-primary-container transition-colors"
              >
                Ho salvato il segreto e i codici di recupero
              </button>
            </>
          ) : (
            <form className="space-y-5" onSubmit={handleVerify}>
              <div className="space-y-1.5">
                <label className="block text-label-sm text-on-surface" htmlFor="totp-code">
                  Inserisci il codice a 6 cifre dell’app di autenticazione
                </label>
                <input
                  id="totp-code"
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
              </div>
              <button
                type="submit"
                disabled={submitting || isLockedOut || code.length !== 6}
                className="w-full py-2.5 px-4 rounded shadow-sm text-label-sm text-on-primary bg-primary hover:bg-primary-container transition-colors disabled:opacity-60"
              >
                {isLockedOut ? `Riprova tra ${lockoutRemaining}s` : submitting ? "Verifica…" : "Attiva 2FA"}
              </button>
            </form>
          )}

          <button
            type="button"
            onClick={() => logout()}
            className="text-center text-label-sm text-on-surface-variant hover:text-primary transition-colors"
          >
            Esci
          </button>
        </div>
      </div>
    </div>
  );
}
