/** Configurazione Admin dei provider AI, dei limiti e del provider attivo. */
import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import {
  useAIProviderModels, useAISettings, useTestAIProvider,
  useUpdateAIProvider, useUpdateAISettings,
} from "@/hooks/useAdmin";
import type { AIProviderConfig } from "@/types";
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import ErrorState from "@/components/ui/ErrorState";
import Icon from "@/components/ui/Icon";
import SettingsTabs from "@/components/settings/SettingsTabs";

export default function AISettingsPage() {
  const { user } = useAuth();
  const query = useAISettings();
  const update = useUpdateAISettings();
  const [limits, setLimits] = useState({ user: 20, rpm: 10, budget: 0 });

  useEffect(() => {
    if (query.data) setLimits({
      user: query.data.userDailyRequestLimit,
      rpm: query.data.providerRequestsPerMinute,
      budget: query.data.globalDailyTokenBudget,
    });
  }, [query.data]);

  if (user?.role !== "admin") return <ErrorState error={new Error("Accesso riservato agli Admin.")} />;
  if (query.isLoading) return <div className="h-64 animate-pulse bg-surface-container-low rounded-lg" />;
  if (query.isError || !query.data) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;

  const saveLimits = () => update.mutate({
    userDailyRequestLimit: limits.user,
    providerRequestsPerMinute: limits.rpm,
    globalDailyTokenBudget: limits.budget,
    expectedRevision: query.data.revision,
  });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-headline-md text-on-surface">Impostazioni</h2>
        <SettingsTabs />
        <p className="text-body-md text-on-surface-variant mt-1">
          Configura il modello globale dei riepiloghi. Le API key sono cifrate e non vengono mai mostrate.
        </p>
      </div>

      <section className="bg-surface-container-lowest border border-border rounded-lg p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-4">
          <Icon name="speed" className="text-primary" />
          <h3 className="text-headline-sm">Limiti operativi</h3>
        </div>
        <div className="grid md:grid-cols-3 gap-4">
          <NumberField label="Richieste giornaliere per utente" value={limits.user} min={1} onChange={(user) => setLimits({ ...limits, user })} />
          <NumberField label="Richieste provider al minuto" value={limits.rpm} min={1} onChange={(rpm) => setLimits({ ...limits, rpm })} />
          <NumberField label="Budget token cloud giornaliero" value={limits.budget} min={0} onChange={(budget) => setLimits({ ...limits, budget })} />
        </div>
        <p className="text-label-sm text-on-surface-variant mt-3">
          Un budget cloud pari a 0 blocca i provider remoti, ma non Ollama locale.
        </p>
        <div className="mt-4 flex items-center gap-3">
          <Button onClick={saveLimits} disabled={update.isPending}>Salva limiti</Button>
          {update.isError && <span className="text-error text-body-sm">{String(update.error)}</span>}
        </div>
      </section>

      <div className="grid xl:grid-cols-2 gap-5">
        {query.data.providers.map((provider) => (
          <ProviderCard
            key={provider.provider}
            provider={provider}
            settingsRevision={query.data.revision}
            cloudBudget={query.data.globalDailyTokenBudget}
          />
        ))}
      </div>
    </div>
  );
}

function NumberField({ label, value, min, onChange }: { label: string; value: number; min: number; onChange: (value: number) => void }) {
  return <label className="text-label-sm text-on-surface-variant">{label}<Input type="number" min={min} value={value} onChange={(e) => onChange(Number(e.target.value))} className="mt-1" /></label>;
}

function ProviderCard({ provider, settingsRevision, cloudBudget }: { provider: AIProviderConfig; settingsRevision: number; cloudBudget: number }) {
  const save = useUpdateAIProvider();
  const test = useTestAIProvider();
  const activate = useUpdateAISettings();
  const catalog = useAIProviderModels(provider.provider);
  const [model, setModel] = useState(provider.model);
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState(provider.baseUrl ?? "");
  const [enabled, setEnabled] = useState(provider.enabled);
  const [organization, setOrganization] = useState(provider.options.organization ?? "");
  const [project, setProject] = useState(provider.options.project ?? "");
  const [siteUrl, setSiteUrl] = useState(provider.options.site_url ?? "");
  const [appName, setAppName] = useState(provider.options.app_name ?? "");

  useEffect(() => {
    setModel(provider.model); setBaseUrl(provider.baseUrl ?? ""); setEnabled(provider.enabled);
  }, [provider]);

  const options: Record<string, string> = {};
  if (provider.provider === "openai") {
    if (organization) options.organization = organization;
    if (project) options.project = project;
  }
  if (provider.provider === "openrouter") {
    if (siteUrl) options.site_url = siteUrl;
    if (appName) options.app_name = appName;
  }
  const isLocal = provider.provider === "ollama";
  const saveProvider = () => save.mutate(
    { provider: provider.provider, input: {
      model, enabled,
      ...(apiKey ? { apiKey } : {}),
      ...(provider.provider === "custom_openai" && baseUrl ? { baseUrl } : {}),
      options, expectedRevision: provider.revision,
    } },
    { onSuccess: () => setApiKey("") },
  );

  return (
    <section className={`bg-surface-container-lowest border rounded-lg p-5 shadow-sm ${provider.active ? "border-primary" : "border-border"}`}>
      <div className="flex items-start justify-between gap-3 mb-4">
        <div><h3 className="text-headline-sm">{provider.displayName}</h3><p className="text-label-sm text-on-surface-variant">{provider.active ? "Provider attivo" : "Non attivo"}</p></div>
        {provider.active && <span className="rounded-full bg-primary/10 text-primary px-2 py-1 text-label-sm">ATTIVO</span>}
      </div>
      {!isLocal && <div className="mb-4 rounded bg-warning/10 border border-warning/30 p-3 text-label-sm text-on-surface-variant">I testi redatti degli annunci saranno inviati a questo provider remoto. Telefoni, immagini e URL personali restano esclusi.</div>}
      {isLocal && <div className="mb-4 rounded bg-primary/5 border border-primary/20 p-3 text-label-sm text-on-surface-variant">Il modello è gestito da Ollama nella rete Docker. Al primo avvio <span className="font-mono">ollama-init</span> completa il download persistente prima di avviare il worker AI.</div>}
      {isLocal && <p className={`mb-3 text-label-sm ${catalog.isError ? "text-error" : catalog.data?.models.includes(model) ? "text-success" : "text-on-surface-variant"}`}>
        {catalog.isFetching ? "Verifica stato Ollama..." : catalog.isError ? "Ollama non raggiungibile." : catalog.data?.models.includes(model) ? "Ollama online: modello disponibile." : "Ollama online: download o inizializzazione del modello in corso."}
      </p>}
      <label className="text-label-sm text-on-surface-variant">ID modello<Input value={model} list={`models-${provider.provider}`} onChange={(e) => setModel(e.target.value)} className="mt-1 font-mono" /></label>
      <datalist id={`models-${provider.provider}`}>{catalog.data?.models.map((name) => <option key={name} value={name} />)}</datalist>
      {provider.provider === "custom_openai" && <label className="block mt-3 text-label-sm text-on-surface-variant">Endpoint HTTPS<Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} className="mt-1 font-mono" /></label>}
      {!isLocal && <label className="block mt-3 text-label-sm text-on-surface-variant">API key {provider.credentialConfigured && <span className="text-success">· configurata</span>}<Input type="password" autoComplete="new-password" value={apiKey} placeholder={provider.credentialConfigured ? "Lascia vuoto per conservarla" : "Inserisci API key"} onChange={(e) => setApiKey(e.target.value)} className="mt-1" /></label>}
      {provider.provider === "openai" && <div className="grid grid-cols-2 gap-2 mt-3"><Input placeholder="Organizzazione (opzionale)" value={organization} onChange={(e) => setOrganization(e.target.value)} /><Input placeholder="Progetto (opzionale)" value={project} onChange={(e) => setProject(e.target.value)} /></div>}
      {provider.provider === "openrouter" && <div className="grid grid-cols-2 gap-2 mt-3"><Input placeholder="URL sito (opzionale)" value={siteUrl} onChange={(e) => setSiteUrl(e.target.value)} /><Input placeholder="Nome applicazione (opzionale)" value={appName} onChange={(e) => setAppName(e.target.value)} /></div>}
      <label className="flex items-center gap-2 mt-4 text-body-md"><input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} disabled={isLocal || (!isLocal && provider.lastTestSuccess !== true)} className="accent-primary" />Provider abilitato</label>
      <div className="flex flex-wrap gap-2 mt-4">
        <Button size="sm" onClick={saveProvider} disabled={save.isPending}>Salva</Button>
        <Button size="sm" variant="secondary" onClick={() => catalog.refreshLive()} disabled={catalog.isFetching || catalog.isRefreshing}>Aggiorna modelli</Button>
        <Button size="sm" variant="secondary" onClick={() => test.mutate(provider.provider)} disabled={test.isPending}>Test connessione</Button>
        {!provider.active && <Button size="sm" variant="secondary" disabled={!provider.enabled || (!isLocal && (provider.lastTestSuccess !== true || cloudBudget <= 0)) || activate.isPending} onClick={() => activate.mutate({ activeProvider: provider.provider, expectedRevision: settingsRevision })}>Attiva</Button>}
        {!isLocal && provider.credentialConfigured && <Button size="sm" variant="danger" onClick={() => {
          if (window.confirm("Rimuovere la credenziale cifrata di questo provider?")) {
            save.mutate({ provider: provider.provider, input: { clearCredential: true, expectedRevision: provider.revision } });
          }
        }}>Rimuovi chiave</Button>}
      </div>
      <p className="text-label-sm text-on-surface-variant mt-2">Il test connessione genera un piccolo output strutturato reale e può consumare quota del provider.</p>
      {provider.lastTestedAt && <p className={`text-label-sm mt-3 ${provider.lastTestSuccess ? "text-success" : "text-error"}`}>Ultimo test: {provider.lastTestSuccess ? "riuscito" : "fallito"} · {new Date(provider.lastTestedAt).toLocaleString()}</p>}
      {test.data?.provider === provider.provider && <p className={`text-label-sm mt-2 ${test.data.success ? "text-success" : "text-error"}`}>{test.data.message} ({test.data.latencyMs} ms)</p>}
      {(save.isError || catalog.isError || catalog.refreshError || activate.isError) && <p className="text-error text-label-sm mt-2">{String(save.error ?? catalog.error ?? catalog.refreshError ?? activate.error)}</p>}
    </section>
  );
}
