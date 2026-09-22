/** Creazione, monitoraggio, retry e download degli export asincroni. */
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useExportJobs, useCreateExportJob, useRetryExportJob } from "@/hooks/useExports";
import * as exportsApi from "@/api/exports";
import Icon from "@/components/ui/Icon";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import { EmptyRow, ErrorRow, LoadingRow, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/Table";
import type { ExportFilters, ExportJob, ExportStatus, ExportType } from "@/types";
import { formatDateTime } from "@/lib/format";

const STATUS_TONE: Record<ExportStatus, BadgeTone> = {
  pending: "neutral",
  ready: "success",
  processing: "warning",
  failed: "error",
};

const TYPE_LABEL: Record<ExportType, string> = {
  text_only: "Solo testo",
  complete_media: "Completa (media)",
  safe_complete: "Completa sicura",
};

const CARDS: { type: ExportType; icon: string; description: string }[] = [
  { type: "text_only", icon: "description", description: "JSON e CSV, senza file media." },
  { type: "complete_media", icon: "perm_media", description: "Dati, varianti visualizzabili e anteprime." },
  { type: "safe_complete", icon: "filter_b_and_w", description: "Solo media pronti e definitivamente sicuri." },
];

function formatBytes(value: number | null): string {
  if (value === null) return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(2)} GB`;
}

export default function ExportsPage() {
  const [params] = useSearchParams();
  const jobs = useExportJobs();
  const createJob = useCreateExportJob();
  const retryJob = useRetryExportJob();
  const [manualIds, setManualIds] = useState("");
  const [phone, setPhone] = useState("");
  const [source, setSource] = useState("");
  const [status, setStatus] = useState<ExportFilters["status"]>();

  const inboundIds = useMemo(
    () => (params.get("recordIds") ?? "").split(",").map((value) => value.trim()).filter(Boolean),
    [params],
  );
  const inboundFilters = useMemo<ExportFilters | undefined>(() => {
    if (params.get("scope") !== "filters") return undefined;
    return {
      phone: params.get("phone") || undefined,
      source: params.get("source") || undefined,
      status: (params.get("status") as ExportFilters["status"]) || undefined,
      dateFrom: params.get("dateFrom") || undefined,
      dateTo: params.get("dateTo") || undefined,
    };
  }, [params]);
  const inboundScope = params.get("scope") as "selected" | "filters" | "all" | null;

  const typedIds = manualIds.split(/[\s,]+/).map((value) => value.trim()).filter(Boolean);
  const localFilters: ExportFilters | undefined = phone || source || status ? { phone: phone || undefined, source: source || undefined, status } : undefined;
  const recordIds = inboundIds.length ? inboundIds : typedIds.length ? typedIds : undefined;
  const filters = recordIds ? undefined : inboundFilters ?? localFilters;
  const scope = recordIds?.length ? "selected" : inboundScope === "all" ? "all" : filters ? "filters" : undefined;
  const hasScope = Boolean(scope);
  const scopeLabel = recordIds?.length
    ? `${recordIds.length} ${recordIds.length === 1 ? "record selezionato" : "record selezionati"}`
    : scope === "all"
      ? "intero archivio"
    : filters
      ? "tutti i record corrispondenti ai filtri espliciti"
      : "nessun ambito selezionato";

  async function handleDownload(job: ExportJob) {
    const { url } = await exportsApi.getExportDownloadUrl(job.id);
    window.open(url, "_blank", "noopener,noreferrer");
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-headline-md text-on-surface mb-1">Gestione esportazioni</h2>
        <p className="text-body-md text-on-surface-variant">Le esportazioni richiedono record selezionati o filtri espliciti. Limiti: 1.000 record e 2 GB.</p>
      </div>

      <section className="bg-surface-container-lowest border border-border rounded-lg p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-headline-sm">Ambito dell’esportazione</h3>
          <Badge tone={hasScope ? "success" : "warning"}>{scopeLabel}</Badge>
        </div>
        {!inboundIds.length && !inboundFilters && (
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="text-label-sm block mb-1">ID record (separati da virgola o su righe distinte)</label>
              <textarea value={manualIds} onChange={(event) => setManualIds(event.target.value)} rows={3} className="w-full rounded border border-border bg-surface p-2 font-mono text-sm" />
            </div>
            <div className="grid gap-2">
              <input value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="Filtro telefono esatto" disabled={typedIds.length > 0} className="rounded border border-border bg-surface p-2" />
              <input value={source} onChange={(event) => setSource(event.target.value)} placeholder="Slug o nome della fonte" disabled={typedIds.length > 0} className="rounded border border-border bg-surface p-2" />
              <select value={status ?? ""} onChange={(event) => setStatus((event.target.value || undefined) as ExportFilters["status"])} disabled={typedIds.length > 0} className="rounded border border-border bg-surface p-2">
                <option value="">Qualsiasi stato</option><option value="verified">Verificato</option><option value="unverified">Non verificato</option><option value="flagged">Segnalato</option>
              </select>
            </div>
          </div>
        )}
      </section>

      <section>
        <h3 className="text-headline-sm text-on-surface mb-4">Nuova esportazione</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-gutter">
          {CARDS.map((card) => (
            <div key={card.type} data-testid={`export-card-${card.type}`} className="bg-surface-container-lowest rounded-lg border border-border p-6">
              <Icon name={card.icon} className="text-primary mb-3" />
              <h4 className="text-body-lg font-medium mb-2">{TYPE_LABEL[card.type]}</h4>
              <p className="text-body-md text-on-surface-variant mb-4">{card.description}</p>
              <button
                onClick={() => createJob.mutate({ type: card.type, scope, recordIds, filters })}
                disabled={!hasScope || createJob.isPending}
                className="bg-primary text-on-primary rounded px-4 py-2 text-label-sm w-full disabled:opacity-40"
              >
                {createJob.isPending ? "Creazione…" : "Crea esportazione"}
              </button>
            </div>
          ))}
        </div>
        {createJob.isError && <p className="text-error text-body-md mt-3">{createJob.error instanceof Error ? createJob.error.message : "Richiesta di esportazione non riuscita."}</p>}
      </section>

      <section>
        <h3 className="text-headline-sm text-on-surface mb-4">Esportazioni recenti</h3>
        <div className="bg-surface-container-lowest border border-border rounded-lg overflow-hidden">
          <Table><THead><Tr><Th>Tipo</Th><Th>Richiesta</Th><Th>Record</Th><Th>Dimensione</Th><Th>Telefono</Th><Th>Stato</Th><Th className="text-right">Azioni</Th></Tr></THead>
            <TBody>
              {jobs.isLoading && <LoadingRow colSpan={7} />}
              {jobs.isError && <ErrorRow colSpan={7} error={jobs.error} onRetry={() => jobs.refetch()} />}
              {jobs.data?.length === 0 && <EmptyRow colSpan={7} message="Nessuna esportazione presente." />}
              {jobs.data?.map((job) => (
                <Tr key={job.id}>
                  <Td>{TYPE_LABEL[job.type]}</Td><Td>{formatDateTime(job.requestedAt)}<div className="text-xs text-on-surface-variant">{job.requestedBy}</div></Td>
                  <Td>{job.recordCount}</Td><Td>{formatBytes(job.archiveSizeBytes ?? job.estimatedUncompressedBytes)}</Td><Td>{job.phoneVisibility}</Td>
                  <Td><Badge tone={STATUS_TONE[job.status]}>{job.status === "processing" ? `Elaborazione ${job.progressPct}%` : job.status === "pending" ? "In attesa" : job.status === "ready" ? "Pronta" : "Non riuscita"}</Badge>{job.errorMessage && <div className="text-xs text-error mt-1 max-w-xs">{job.errorMessage}</div>}</Td>
                  <Td className="text-right">
                    {job.status === "ready" && <button onClick={() => handleDownload(job)} className="text-primary">Scarica</button>}
                    {job.status === "failed" && <button onClick={() => retryJob.mutate(job.id)} className="text-primary">Riprova</button>}
                  </Td>
                </Tr>
              ))}
            </TBody>
          </Table>
        </div>
      </section>
    </div>
  );
}
