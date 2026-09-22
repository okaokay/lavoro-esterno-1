import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useIngestionSettings, useSanitizeExisting, useUpdateIngestionSettings } from "@/hooks/useIntegrations";
import SettingsTabs from "@/components/settings/SettingsTabs";
import ErrorState from "@/components/ui/ErrorState";
import Input from "@/components/ui/Input";
import Button from "@/components/ui/Button";

export default function IngestionSettingsPage() {
  const { user } = useAuth(); const query = useIngestionSettings(); const update = useUpdateIngestionSettings(); const backfill = useSanitizeExisting();
  const [size, setSize] = useState(50);
  useEffect(() => { if (query.data) setSize(query.data.publishBatchSize); }, [query.data]);
  if (user?.role !== "admin") return <ErrorState error={new Error("Accesso riservato agli Admin.")} />;
  if (query.isError || !query.data) return query.isLoading ? <div className="h-40 animate-pulse bg-surface-container-low rounded" /> : <ErrorState error={query.error} />;
  return <div className="space-y-6"><div><h2 className="text-headline-md">Impostazioni</h2><SettingsTabs /></div>
    <section className="rounded-lg border border-border bg-surface-container-lowest p-5"><h3 className="text-headline-sm">Pubblicazione record</h3><p className="my-3 text-body-sm text-on-surface-variant">I batch completi vengono pubblicati subito; il resto finale viene sempre salvato.</p><div className="flex max-w-md items-end gap-3"><label className="flex-1 text-label-sm">Annunci per batch<Input type="number" min={1} max={500} value={size} onChange={(e) => setSize(Number(e.target.value))} /></label><Button onClick={() => update.mutate({ publishBatchSize: size, expectedRevision: query.data.revision })}>Salva</Button></div></section>
    <section className="rounded-lg border border-border bg-surface-container-lowest p-5"><h3 className="text-headline-sm">Pulizia contenuti con Gemma</h3><p className="my-3 text-body-sm text-on-surface-variant">Provider Ollama · modello {query.data.sanitizationModel}. Titoli e descrizioni vengono sempre valutati; gli altri campi solo se marcati nella fonte.</p><Button variant="secondary" disabled={backfill.isPending} onClick={() => backfill.mutate()}>Bonifica record esistenti</Button>{backfill.data && <span className="ml-3 text-body-sm">Job accodato: {backfill.data.taskId}</span>}</section></div>;
}
