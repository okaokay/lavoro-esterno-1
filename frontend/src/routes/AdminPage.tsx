import { useMemo, useState, type FormEvent } from "react";
import {
  useAdminUsers,
  useUpdateAdminUserRole,
  useSuspendAdminUser,
  useActivateAdminUser,
  useAuditLog,
  useCreateAdminUser,
  useResetAdminUserTwoFactor,
  useUpdateClearPhonePermission,
  useConfirmErasureRequest,
  useCreateErasureRequest,
  useErasureRequests,
} from "@/hooks/useAdmin";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/api/client";
import { describeError } from "@/lib/errors";
import Icon from "@/components/ui/Icon";
import Avatar from "@/components/ui/Avatar";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import Select from "@/components/ui/Select";
import Button from "@/components/ui/Button";
import Dialog from "@/components/ui/Dialog";
import ErrorState from "@/components/ui/ErrorState";
import { EmptyRow, ErrorRow, LoadingRow, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/Table";
import { cn } from "@/lib/cn";
import type { AdminUser, UserRole } from "@/types";
import type { SourcePriority } from "@/types";
import { useClassifierSettings, useReprocessClassifierMedia, useSourcePriorities, useUpdateClassifierSettings, useUpdateSourcePriority } from "@/hooks/useOperations";
import { formatDateTime } from "@/lib/format";
import { classifierGroupLabel, statusLabel } from "@/lib/labels";
import { auditActionLabel } from "@/lib/auditLabels";

// Replicates desing/admin_lavoro_esterno/code.html.
//
// The mockup's tab strip is reused here with local useState instead of the
// router-driven <Tabs> component: /admin is a single flat route (no nested
// paths per tab in App.tsx), so there is nothing for NavLink to match against.

type AdminTab = "users" | "privacy" | "source-priorities" | "classifiers" | "audit-log";

const TABS: { key: AdminTab; label: string }[] = [
  { key: "users", label: "Utenti e ruoli" },
  { key: "privacy", label: "Privacy / Cancellazione" },
  { key: "source-priorities", label: "Priorità fonti" },
  { key: "classifiers", label: "Classificatori" },
  { key: "audit-log", label: "Registro di audit" },
];

const ROLE_LABEL: Record<UserRole, string> = {
  admin: "Admin",
  operator: "Operator",
  viewer: "Visualizzatore",
};

const STATUS_TONE: Record<AdminUser["status"], BadgeTone> = {
  active: "success",
  suspended: "warning",
  invited: "neutral",
};

// True when the mutation failed specifically because the requesting admin
// hasn't enabled 2FA yet (server-side `require_admin_with_2fa`) — see
// src/api/admin.ts:createAdminUser. Worth a dedicated message instead of the
// generic "Access denied" describeError() would otherwise show for a 403.
function isMfaSetupRequiredError(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 403) return false;
  const detail = (error.body as { detail?: { error_code?: string } } | undefined)?.detail;
  return detail?.error_code === "mfa_setup_required";
}

export default function AdminPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<AdminTab>("users");

  if (user && user.role !== "admin") {
    return (
      <div className="bg-surface-container-lowest border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)]">
        <ErrorState
          error={new ApiError(403, "Per visualizzare questa pagina sono necessari privilegi di amministratore.")}
          className="py-16"
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4">
        <div className="flex justify-between items-end">
          <div>
            <h2 className="text-headline-md text-on-surface">Amministrazione</h2>
            <p className="text-body-md text-on-surface-variant mt-1">
              Manage platform configuration, user access, and audit trails.
            </p>
          </div>
        </div>

        {/* Local tab strip — styled like components/ui/Tabs.tsx but click-driven */}
        <div className="border-b border-border flex gap-1">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                "px-4 py-2.5 text-label-sm font-medium border-b-2 -mb-px transition-colors",
                tab === t.key
                  ? "border-primary text-primary"
                  : "border-transparent text-on-surface-variant hover:text-on-surface",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === "users" && <UsersTab />}
      {tab === "privacy" && <PrivacyTab />}
      {tab === "source-priorities" && (
        <SourcePrioritiesTab />
      )}
      {tab === "classifiers" && (
        <ClassifiersTab />
      )}
      {tab === "audit-log" && <AuditLogTab />}
    </div>
  );
}

function UsersTab() {
  const users = useAdminUsers();
  const updateRole = useUpdateAdminUserRole();
  const suspend = useSuspendAdminUser();
  const activate = useActivateAdminUser();
  const updatePhonePermission = useUpdateClearPhonePermission();
  const [createOpen, setCreateOpen] = useState(false);
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <Button onClick={() => setCreateOpen(true)}>
          <Icon name="person_add" size={18} />
          Crea utente
        </Button>
      </div>
      {(suspend.isError || activate.isError) && (
        <p className="rounded border border-error/30 bg-error/10 p-3 text-error">
          {describeError(suspend.error ?? activate.error).description}
        </p>
      )}

      <div className="bg-surface-container-lowest border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] flex flex-col">
        <Table>
          <THead>
            <Tr className="hover:bg-transparent">
              <Th>Utente</Th>
              <Th>Email</Th>
              <Th>Ruolo</Th>
              <Th>Stato</Th>
              <Th>Ultimo accesso</Th>
              <Th className="text-center">MFA</Th>
              <Th className="text-center">Telefono in chiaro</Th>
              <Th className="text-right">Azioni</Th>
            </Tr>
          </THead>
          <TBody>
            {users.isLoading && <LoadingRow colSpan={8} />}
            {users.isError && <ErrorRow colSpan={8} error={users.error} onRetry={() => users.refetch()} />}
            {users.data && users.data.length === 0 && <EmptyRow colSpan={8} message="Nessun utente trovato." />}
            {users.data?.map((user) => (
              <Tr key={user.id}>
                <Td>
                  <div className="flex items-center gap-3">
                    <Avatar name={user.name} size={28} />
                    <span className="font-medium text-on-surface">{user.name}</span>
                  </div>
                </Td>
                <Td className="text-on-surface-variant font-mono text-mono-data">{user.email}</Td>
                <Td>
                  <Select
                    value={user.role}
                    disabled={updateRole.isPending}
                    onChange={(e) => updateRole.mutate({ id: user.id, role: e.target.value as UserRole })}
                    className="text-label-sm py-1"
                  >
                    {(Object.keys(ROLE_LABEL) as UserRole[]).map((role) => (
                      <option key={role} value={role}>
                        {ROLE_LABEL[role]}
                      </option>
                    ))}
                  </Select>
                </Td>
                <Td>
                  <Badge tone={STATUS_TONE[user.status]}>{user.status === "active" ? "ATTIVO" : user.status === "suspended" ? "SOSPESO" : "INVITATO"}</Badge>
                </Td>
                <Td className="text-on-surface-variant font-mono text-mono-data">{formatDateTime(user.lastLoginAt)}</Td>
                <Td className="text-center">
                  {user.mfaEnabled ? (
                    <Icon name="verified_user" size={18} className="text-success" />
                  ) : (
                    <Icon name="gpp_maybe" size={18} className="text-outline" />
                  )}
                </Td>
                <Td className="text-center">
                  <input
                    type="checkbox"
                    aria-label={`Consenti a ${user.email} di visualizzare i numeri in chiaro`}
                    checked={user.canViewClearPhone}
                    disabled={user.role === "admin" || updatePhonePermission.isPending}
                    onChange={(event) =>
                      updatePhonePermission.mutate({ id: user.id, enabled: event.target.checked })
                    }
                    title={user.role === "admin" ? "Gli amministratori dispongono sempre di questo permesso" : undefined}
                    className="h-4 w-4 accent-primary"
                  />
                </Td>
                <Td className="text-right">
                  <div className="flex items-center justify-end gap-3">
                    <button
                      onClick={() => setResetTarget(user)}
                      disabled={!user.mfaEnabled}
                      title={user.mfaEnabled ? "Reimposta 2FA" : "2FA non attiva per questo utente"}
                      className="text-label-sm font-medium text-on-surface-variant hover:text-primary transition-colors disabled:opacity-40 disabled:pointer-events-none"
                    >
                      Reimposta 2FA
                    </button>
                    <button
                      onClick={() => {
                        const action = user.status === "suspended" ? "riattivare" : "sospendere";
                        if (!window.confirm(`Vuoi ${action} ${user.email}?`)) return;
                        if (user.status === "suspended") activate.mutate(user.id);
                        else suspend.mutate(user.id);
                      }}
                      disabled={suspend.isPending || activate.isPending}
                      className="text-label-sm font-medium text-on-surface-variant hover:text-error transition-colors disabled:opacity-40"
                    >
                      {user.status === "suspended" ? "Riattiva" : "Sospendi"}
                    </button>
                  </div>
                </Td>
              </Tr>
            ))}
          </TBody>
        </Table>
      </div>

      <CreateUserDialog open={createOpen} onClose={() => setCreateOpen(false)} />
      <ResetTwoFactorDialog user={resetTarget} onClose={() => setResetTarget(null)} />
    </div>
  );
}

function CreateUserDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const createUser = useCreateAdminUser();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("viewer");

  function handleClose() {
    createUser.reset();
    setEmail("");
    setPassword("");
    setRole("viewer");
    onClose();
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    createUser.mutate(
      { email, password, role },
      {
        onSuccess: handleClose,
      },
    );
  }

  const mfaSetupRequired = isMfaSetupRequiredError(createUser.error);

  return (
    <Dialog open={open} onClose={handleClose} title="Crea utente">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div>
          <label htmlFor="create-user-email" className="text-label-sm text-on-surface-variant block mb-1">
            Email
          </label>
          <input
            id="create-user-email"
            data-dialog-initial-focus
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full py-2 px-3 border border-outline-variant rounded bg-surface text-body-md text-on-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container outline-none transition-colors"
          />
        </div>
        <div>
          <label htmlFor="create-user-password" className="text-label-sm text-on-surface-variant block mb-1">
            Password
          </label>
          <input
            id="create-user-password"
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full py-2 px-3 border border-outline-variant rounded bg-surface text-body-md text-on-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container outline-none transition-colors"
          />
        </div>
        <div>
          <label htmlFor="create-user-role" className="text-label-sm text-on-surface-variant block mb-1">
            Ruolo
          </label>
          <Select id="create-user-role" value={role} onChange={(e) => setRole(e.target.value as UserRole)} className="w-full">
            {(Object.keys(ROLE_LABEL) as UserRole[]).map((r) => (
              <option key={r} value={r}>
                {ROLE_LABEL[r]}
              </option>
            ))}
          </Select>
        </div>

        {createUser.isError && (
          <p className="text-body-md text-error">
            {mfaSetupRequired
              ? "Devi avere la 2FA attiva per creare utenti."
              : describeError(createUser.error).description}
          </p>
        )}

        <div className="flex justify-end gap-2 mt-2">
          <Button type="button" variant="secondary" onClick={handleClose}>
            Annulla
          </Button>
          <Button type="submit" disabled={createUser.isPending}>
            {createUser.isPending ? "Creazione…" : "Crea utente"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function ResetTwoFactorDialog({ user, onClose }: { user: AdminUser | null; onClose: () => void }) {
  const resetTwoFactor = useResetAdminUserTwoFactor();

  function handleClose() {
    resetTwoFactor.reset();
    onClose();
  }

  function handleConfirm() {
    if (!user) return;
    resetTwoFactor.mutate(user.id, { onSuccess: handleClose });
  }

  return (
    <Dialog open={user !== null} onClose={handleClose} title="Reimposta 2FA">
      <div className="flex flex-col gap-4">
        <p className="text-body-md text-on-surface">
          Vuoi disattivare la 2FA per <span className="font-semibold">{user?.name}</span> (
          {user?.email})? Dovrà configurarla nuovamente al prossimo accesso.
        </p>
        {resetTwoFactor.isError && (
          <p className="text-body-md text-error">{describeError(resetTwoFactor.error).description}</p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={handleClose}>
            Annulla
          </Button>
          <Button type="button" variant="danger" onClick={handleConfirm} disabled={resetTwoFactor.isPending}>
            {resetTwoFactor.isPending ? "Reimpostazione…" : "Reimposta 2FA"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function PrivacyTab() {
  const requests = useErasureRequests();
  const createRequest = useCreateErasureRequest();
  const confirmRequest = useConfirmErasureRequest();
  const [phone, setPhone] = useState("");
  const [reason, setReason] = useState("");
  const [reference, setReference] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    createRequest.mutate(
      { phone, reason, authorizationReference: reference },
      { onSuccess: () => { setPhone(""); setReason(""); setReference(""); } },
    );
  }

  return (
    <div className="space-y-5">
      <form onSubmit={submit} className="bg-surface-container-lowest border border-border rounded-lg p-5 grid md:grid-cols-3 gap-4">
        <div className="md:col-span-3">
          <h3 className="text-headline-sm">Nuova anteprima di cancellazione</h3>
          <p className="text-body-md text-on-surface-variant">La bozza non elimina dati. Verifica l’impatto, quindi conferma esplicitamente.</p>
        </div>
        <input required value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="Numero di telefono" className="rounded border border-border bg-surface p-2" />
        <input required minLength={3} value={reference} onChange={(event) => setReference(event.target.value)} placeholder="Riferimento autorizzativo" className="rounded border border-border bg-surface p-2" />
        <input required minLength={3} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Motivazione" className="rounded border border-border bg-surface p-2" />
        <div className="md:col-span-3 flex justify-end"><Button type="submit" disabled={createRequest.isPending}>Crea anteprima</Button></div>
        {createRequest.isError && <p className="md:col-span-3 text-error">{describeError(createRequest.error).description}</p>}
      </form>

      <div className="bg-surface-container-lowest border border-border rounded-lg overflow-hidden">
        <Table><THead><Tr><Th>Creata</Th><Th>Riferimento</Th><Th>Impatto</Th><Th>Stato</Th><Th className="text-right">Azione</Th></Tr></THead>
          <TBody>
            {requests.isLoading && <LoadingRow colSpan={5} />}
            {requests.isError && <ErrorRow colSpan={5} error={requests.error} onRetry={() => requests.refetch()} />}
            {requests.data?.length === 0 && <EmptyRow colSpan={5} message="Nessuna richiesta di cancellazione." />}
            {requests.data?.map((request) => (
              <Tr key={request.id}>
                <Td>{formatDateTime(request.createdAt)}</Td><Td>{request.authorizationReference}</Td>
                <Td className="font-mono text-xs">{Object.entries(request.impact).map(([key, value]) => `${key}: ${value}`).join(" · ")}</Td>
                <Td><Badge tone={request.status === "completed" ? "success" : request.status === "failed" ? "error" : "warning"}>{statusLabel(request.status)}</Badge>{request.errorMessage && <div className="text-xs text-error">{request.errorMessage}</div>}</Td>
                <Td className="text-right">{(request.status === "draft" || request.status === "failed") && <button onClick={() => confirmRequest.mutate(request.id)} disabled={confirmRequest.isPending} className="text-primary font-medium">Conferma cancellazione</button>}</Td>
              </Tr>
            ))}
          </TBody>
        </Table>
      </div>
    </div>
  );
}

function AuditLogTab() {
  const auditLog = useAuditLog();
  const [query, setQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const filtered = useMemo(() => {
    if (!auditLog.data) return undefined;
    const q = query.trim().toLowerCase();
    const from = dateFrom ? new Date(dateFrom).getTime() : null;
    // Include the entire "to" day rather than only events at exactly midnight.
    const to = dateTo ? new Date(dateTo).getTime() + 24 * 60 * 60 * 1000 - 1 : null;

    return auditLog.data.filter((entry) => {
      if (q && !entry.actor.toLowerCase().includes(q) && !auditActionLabel(entry.action).toLowerCase().includes(q)) {
        return false;
      }
      const occurredAt = new Date(entry.occurredAt).getTime();
      if (from !== null && occurredAt < from) return false;
      if (to !== null && occurredAt > to) return false;
      return true;
    });
  }, [auditLog.data, query, dateFrom, dateTo]);

  return (
    <div className="bg-surface-container-lowest border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] flex flex-col">
      <div className="p-4 border-b border-border flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[200px]">
          <label htmlFor="audit-log-query" className="text-label-sm text-on-surface-variant block mb-1">
            Cerca autore / azione
          </label>
          <input
            id="audit-log-query"
            type="text"
            placeholder="Filtra per autore o azione…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full py-2 px-3 border border-outline-variant rounded bg-surface text-body-md text-on-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container outline-none transition-colors"
          />
        </div>
        <div>
          <label htmlFor="audit-log-from" className="text-label-sm text-on-surface-variant block mb-1">
            Dal
          </label>
          <input
            id="audit-log-from"
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="py-2 px-3 border border-outline-variant rounded bg-surface text-body-md text-on-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container outline-none transition-colors"
          />
        </div>
        <div>
          <label htmlFor="audit-log-to" className="text-label-sm text-on-surface-variant block mb-1">
            Al
          </label>
          <input
            id="audit-log-to"
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="py-2 px-3 border border-outline-variant rounded bg-surface text-body-md text-on-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container outline-none transition-colors"
          />
        </div>
        {(query || dateFrom || dateTo) && (
          <button
            onClick={() => {
              setQuery("");
              setDateFrom("");
              setDateTo("");
            }}
            className="text-label-sm text-on-surface-variant hover:text-primary transition-colors py-2"
          >
            Azzera filtri
          </button>
        )}
      </div>
      <Table>
        <THead>
          <Tr className="hover:bg-transparent">
            <Th>Autore</Th>
            <Th>Azione</Th>
            <Th>Destinazione</Th>
            <Th>Data e ora</Th>
          </Tr>
        </THead>
        <TBody>
          {auditLog.isLoading && <LoadingRow colSpan={4} />}
          {auditLog.isError && <ErrorRow colSpan={4} error={auditLog.error} onRetry={() => auditLog.refetch()} />}
          {filtered && filtered.length === 0 && (
            <EmptyRow colSpan={4} message={auditLog.data && auditLog.data.length > 0 ? "Nessun evento di audit corrisponde ai filtri." : "Nessun evento di audit presente."} />
          )}
          {filtered?.map((entry) => (
            <Tr key={entry.id}>
              <Td className="text-on-surface font-medium">{entry.actor}</Td>
              <Td className="text-on-surface-variant">{auditActionLabel(entry.action)}</Td>
              <Td className="text-on-surface-variant font-mono text-mono-data">{entry.target}</Td>
              <Td className="text-on-surface-variant font-mono text-mono-data">{formatDateTime(entry.occurredAt)}</Td>
            </Tr>
          ))}
        </TBody>
      </Table>
    </div>
  );
}

function SourcePrioritiesTab() {
  const priorities = useSourcePriorities();
  const update = useUpdateSourcePriority();
  return <div className="bg-surface-container-lowest border border-border rounded-lg overflow-hidden"><Table><THead><Tr><Th>Fonte</Th><Th>Stato</Th><Th>Priorità</Th><Th>Record</Th><Th>Ricalcolo</Th></Tr></THead><TBody>
    {priorities.isLoading && <LoadingRow colSpan={5} />}
    {priorities.isError && <ErrorRow colSpan={5} error={priorities.error} onRetry={() => priorities.refetch()} />}
    {priorities.data?.map((source) => <Tr key={source.sourceId}><Td><strong>{source.name}</strong><div className="text-xs text-on-surface-variant">{source.code}</div></Td><Td><Badge tone={source.status === "healthy" ? "success" : "warning"}>{statusLabel(source.status)}</Badge></Td><Td><Select value={source.priority} disabled={update.isPending} onChange={(e) => update.mutate({ sourceId: source.sourceId, priority: e.target.value as SourcePriority })}>{["high", "medium", "low"].map((p) => <option key={p} value={p}>{p === "high" ? "alta" : p === "medium" ? "media" : "bassa"}</option>)}</Select></Td><Td>{source.affectedRecords}</Td><Td>{source.latestJob ? <div className="text-xs"><Badge tone={source.latestJob.status === "completed" ? "success" : source.latestJob.status === "failed" ? "error" : "warning"}>{statusLabel(source.latestJob.status)}</Badge><div>{source.latestJob.recordsProcessed}/{source.latestJob.recordsTotal} · {source.latestJob.canonicalsChanged} modificati</div></div> : "—"}</Td></Tr>)}
  </TBody></Table></div>;
}

function ClassifiersTab() {
  const config = useClassifierSettings();
  const update = useUpdateClassifierSettings();
  const reprocess = useReprocessClassifierMedia();
  const [safe, setSafe] = useState("");
  const [explicit, setExplicit] = useState("");
  const currentSafe = config.data?.safeThreshold ?? Number(safe);
  const currentExplicit = config.data?.explicitThreshold ?? Number(explicit);
  if (config.isLoading) return <div className="h-40 animate-pulse bg-surface-container-low rounded" />;
  if (config.isError || !config.data) return <ErrorState error={config.error} onRetry={() => config.refetch()} />;
  return <div className="space-y-5"><section className="bg-surface-container-lowest border border-border rounded-lg p-5"><h3 className="text-headline-sm">{config.data.modelName}</h3><p className="font-mono text-sm text-on-surface-variant">{config.data.modelVersion} · revisione {config.data.revision}</p><form className="grid sm:grid-cols-3 gap-4 mt-4" onSubmit={(e) => { e.preventDefault(); update.mutate({ safeThreshold: Number(safe || currentSafe), explicitThreshold: Number(explicit || currentExplicit), expectedRevision: config.data.revision }); }}><label className="text-sm">Soglia contenuto sicuro<input type="number" min="0" max="1" step="0.01" defaultValue={currentSafe} onChange={(e) => setSafe(e.target.value)} className="block w-full rounded border border-border bg-surface p-2" /></label><label className="text-sm">Soglia contenuto esplicito<input type="number" min="0" max="1" step="0.01" defaultValue={currentExplicit} onChange={(e) => setExplicit(e.target.value)} className="block w-full rounded border border-border bg-surface p-2" /></label><div className="self-end"><Button type="submit" disabled={update.isPending}>Salva soglie</Button></div></form>{update.isError && <p className="text-error mt-2">{describeError(update.error).description}</p>}</section><section className="grid md:grid-cols-3 gap-4">{Object.entries(config.data.stats).map(([group, values]) => <div key={group} className="bg-surface-container-lowest border border-border rounded-lg p-4"><h4 className="font-semibold mb-2">{classifierGroupLabel(group)}</h4>{Object.entries(values).map(([key, value]) => <div key={key} className="flex justify-between text-sm"><span>{statusLabel(key)}</span><strong>{value}</strong></div>)}</div>)}</section><div className="flex gap-3"><Button variant="secondary" onClick={() => reprocess.mutate("failed")}>Rielabora non riusciti</Button><Button variant="secondary" onClick={() => reprocess.mutate("needs_review")}>Rielabora da revisionare</Button>{reprocess.data && <span className="self-center text-sm">Accodati: {reprocess.data.queued}</span>}</div></div>;
}
