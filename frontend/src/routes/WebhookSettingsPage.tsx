import { useState, type FormEvent } from "react";
import { useAuth } from "@/context/AuthContext";
import { useSources } from "@/hooks/useSources";
import {
  useCreateWebhook,
  useDeleteWebhook,
  useUpdateWebhook,
  useWebhookEndpoints,
} from "@/hooks/useIntegrations";
import SettingsTabs from "@/components/settings/SettingsTabs";
import ErrorState from "@/components/ui/ErrorState";
import Input from "@/components/ui/Input";
import Button from "@/components/ui/Button";
import { describeError } from "@/lib/errors";

type PhonePolicy = "clear" | "masked" | "excluded";

const emptyForm = {
  name: "",
  url: "",
  secret: "",
  clearSecret: false,
  enabled: true,
  allSources: true,
  sourceIds: [] as string[],
  phonePolicy: "masked" as PhonePolicy,
};

export default function WebhookSettingsPage() {
  const { user } = useAuth();
  const endpoints = useWebhookEndpoints();
  const sources = useSources();
  const create = useCreateWebhook();
  const update = useUpdateWebhook();
  const remove = useDeleteWebhook();
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  if (user?.role !== "admin") {
    return <ErrorState error={new Error("Accesso riservato agli Admin.")} />;
  }
  if (endpoints.isError) return <ErrorState error={endpoints.error} />;

  function resetForm() {
    setEditingId(null);
    setForm(emptyForm);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage(null);
    const input = {
      name: form.name,
      url: form.url,
      enabled: form.enabled,
      allSources: form.allSources,
      sourceIds: form.sourceIds,
      phonePolicy: form.phonePolicy,
      ...(form.secret ? { secret: form.secret } : {}),
      ...(editingId && form.clearSecret ? { clearSecret: true } : {}),
    };
    try {
      if (editingId) await update.mutateAsync({ id: editingId, input });
      else await create.mutateAsync(input);
      resetForm();
    } catch (error) {
      setMessage(describeError(error).description);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-headline-md">Impostazioni</h2>
        <SettingsTabs />
      </div>
      {message && (
        <div role="alert" className="rounded border border-error/30 p-3 text-error">
          {message}
        </div>
      )}
      <section className="rounded-lg border border-border bg-surface-container-lowest p-5">
        <h3 className="mb-4 text-headline-sm">
          {editingId ? "Modifica destinazione webhook" : "Nuova destinazione webhook"}
        </h3>
        <form onSubmit={submit} className="grid gap-3 md:grid-cols-2">
          <Input
            required
            placeholder="Nome"
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
          <Input
            required
            type="url"
            placeholder="https://example.com/webhook"
            value={form.url}
            onChange={(event) => setForm({ ...form, url: event.target.value })}
          />
          <Input
            type="password"
            minLength={16}
            placeholder={editingId ? "Nuovo segreto HMAC (vuoto = invariato)" : "Segreto HMAC opzionale"}
            value={form.secret}
            disabled={form.clearSecret}
            onChange={(event) => setForm({ ...form, secret: event.target.value })}
          />
          <select
            className="rounded border border-border bg-surface p-2"
            value={form.phonePolicy}
            onChange={(event) => setForm({ ...form, phonePolicy: event.target.value as PhonePolicy })}
          >
            <option value="masked">Telefono mascherato</option>
            <option value="excluded">Telefono escluso</option>
            <option value="clear">Telefono in chiaro</option>
          </select>
          <label className="flex gap-2">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
            />
            Destinazione abilitata
          </label>
          <label className="flex gap-2">
            <input
              type="checkbox"
              checked={form.allSources}
              onChange={(event) => setForm({ ...form, allSources: event.target.checked, sourceIds: [] })}
            />
            Tutte le fonti
          </label>
          {editingId && (
            <label className="flex gap-2">
              <input
                type="checkbox"
                checked={form.clearSecret}
                onChange={(event) => setForm({ ...form, clearSecret: event.target.checked, secret: "" })}
              />
              Rimuovi il segreto HMAC esistente
            </label>
          )}
          {!form.allSources && (
            <div className="flex flex-wrap gap-3 md:col-span-2">
              {sources.data?.map((source) => (
                <label key={source.id} className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={form.sourceIds.includes(source.id)}
                    onChange={() =>
                      setForm({
                        ...form,
                        sourceIds: form.sourceIds.includes(source.id)
                          ? form.sourceIds.filter((id) => id !== source.id)
                          : [...form.sourceIds, source.id],
                      })
                    }
                  />
                  {source.name}
                </label>
              ))}
            </div>
          )}
          <div className="flex gap-2">
            <Button type="submit" disabled={create.isPending || update.isPending}>
              {editingId ? "Salva" : "Aggiungi"}
            </Button>
            {editingId && (
              <Button type="button" variant="secondary" onClick={resetForm}>
                Annulla
              </Button>
            )}
          </div>
        </form>
      </section>
      <section className="space-y-2">
        {endpoints.data?.map((endpoint) => (
          <div
            key={endpoint.id}
            className="flex items-center gap-3 rounded border border-border bg-surface-container-lowest p-3"
          >
            <div className="flex-1">
              <strong>{endpoint.name}</strong>
              <div className="text-label-sm text-on-surface-variant">
                {endpoint.url} ·{" "}
                {endpoint.allSources ? "tutte le fonti" : `${endpoint.sourceIds.length} fonti`} · telefono{" "}
                {endpoint.phonePolicy} · HMAC {endpoint.secretConfigured ? "attivo" : "assente"} ·{" "}
                {endpoint.enabled ? "abilitato" : "disabilitato"}
              </div>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setEditingId(endpoint.id);
                setForm({
                  name: endpoint.name,
                  url: endpoint.url,
                  secret: "",
                  clearSecret: false,
                  enabled: endpoint.enabled,
                  allSources: endpoint.allSources,
                  sourceIds: endpoint.sourceIds,
                  phonePolicy: endpoint.phonePolicy,
                });
              }}
            >
              Modifica
            </Button>
            <Button variant="danger" size="sm" onClick={() => remove.mutate(endpoint.id)}>
              Elimina
            </Button>
          </div>
        ))}
      </section>
    </div>
  );
}
