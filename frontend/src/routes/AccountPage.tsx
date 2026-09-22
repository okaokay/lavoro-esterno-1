/** Profilo corrente e operazioni self-service su password e 2FA. */
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import * as authApi from "@/api/auth";
import Button from "@/components/ui/Button";
import Icon from "@/components/ui/Icon";
import { describeError } from "@/lib/errors";
import { roleLabel, statusLabel } from "@/lib/labels";

export default function AccountPage() {
  const { user, logout } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (newPassword !== confirmPassword) { setError("Le nuove password non coincidono."); return; }
    setBusy(true);
    try {
      await authApi.changePassword(currentPassword, newPassword);
      await logout();
    } catch (err) { setError(describeError(err).description); }
    finally { setBusy(false); }
  }

  async function regenerateCodes(event: FormEvent) {
    event.preventDefault();
    setError(""); setMessage(""); setBusy(true);
    try {
      setBackupCodes(await authApi.regenerateBackupCodes(totp));
      setTotp(""); setMessage("I vecchi backup code sono stati invalidati.");
    } catch (err) { setError(describeError(err).description); }
    finally { setBusy(false); }
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div><h2 className="text-headline-md">Account</h2><p className="text-on-surface-variant">Profilo e sicurezza dell’account corrente.</p></div>
      <section className="bg-surface-container-lowest border border-border rounded-lg p-5">
        <h3 className="text-headline-sm mb-4">Profilo</h3>
        <dl className="grid sm:grid-cols-2 gap-4 text-body-md">
          <div><dt className="text-on-surface-variant">Nome</dt><dd>{user?.name}</dd></div>
          <div><dt className="text-on-surface-variant">Email</dt><dd>{user?.email}</dd></div>
          <div><dt className="text-on-surface-variant">Ruolo</dt><dd>{roleLabel(user?.role)}</dd></div>
          <div><dt className="text-on-surface-variant">Stato</dt><dd>{statusLabel(user?.status)}</dd></div>
        </dl>
      </section>
      {error && <div className="rounded border border-error/30 bg-error/10 p-3 text-error">{error}</div>}
      {message && <div className="rounded border border-success/30 bg-success/10 p-3 text-success">{message}</div>}
      <div className="grid lg:grid-cols-2 gap-6">
        <form onSubmit={changePassword} className="bg-surface-container-lowest border border-border rounded-lg p-5 space-y-3">
          <h3 className="text-headline-sm">Cambia password</h3>
          <input type="password" required value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} placeholder="Password attuale" className="w-full rounded border border-border bg-surface p-2" />
          <input type="password" required minLength={12} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="Nuova password" className="w-full rounded border border-border bg-surface p-2" />
          <input type="password" required minLength={12} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="Conferma nuova password" className="w-full rounded border border-border bg-surface p-2" />
          <p className="text-xs text-on-surface-variant">Dopo il cambio verranno chiuse tutte le sessioni.</p>
          <Button type="submit" disabled={busy}>Aggiorna password</Button>
        </form>
        <section className="bg-surface-container-lowest border border-border rounded-lg p-5 space-y-3">
          <div className="flex items-center gap-2"><Icon name="verified_user" /><h3 className="text-headline-sm">Autenticazione a due fattori</h3></div>
          {!user?.mfaEnabled ? (
            <><p className="text-on-surface-variant">La 2FA non è attiva.</p><Link to="/2fa-setup" className="inline-flex rounded bg-primary text-on-primary px-4 py-2">Attiva 2FA</Link></>
          ) : (
            <form onSubmit={regenerateCodes} className="space-y-3">
              <p className="text-success">2FA attiva</p>
              <label className="block text-sm">Codice TOTP corrente</label>
              <input required inputMode="numeric" pattern="\d{6}" maxLength={6} value={totp} onChange={(e) => setTotp(e.target.value.replace(/\D/g, "").slice(0, 6))} className="w-full rounded border border-border bg-surface p-2 font-mono" />
              <Button type="submit" variant="secondary" disabled={busy || totp.length !== 6}>Rigenera codici di recupero</Button>
            </form>
          )}
          {backupCodes.length > 0 && <div className="border border-warning rounded p-3"><p className="font-semibold mb-2">Salvali ora: non saranno mostrati di nuovo.</p><div className="grid grid-cols-2 font-mono gap-1">{backupCodes.map((code) => <span key={code}>{code}</span>)}</div></div>}
        </section>
      </div>
    </div>
  );
}
