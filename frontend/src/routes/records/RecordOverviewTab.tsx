import { useParams } from "react-router-dom";
import { useRecordOverview } from "@/hooks/useRecords";
import Icon from "@/components/ui/Icon";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import ProgressBar from "@/components/ui/ProgressBar";
import ErrorState from "@/components/ui/ErrorState";
import AggregatedCustomFields from "@/components/records/AggregatedCustomFields";
import { formatDateTime } from "@/lib/format";

// Replicates desing/record_detail_overview/code.html: a canonical listing
// card (title/description/confidence) plus a right-hand entity summary card.

const STATUS_TONE: Record<string, BadgeTone> = {
  verified: "success",
  unverified: "warning",
  flagged: "error",
};

const STATUS_LABEL: Record<string, string> = {
  verified: "Annuncio attivo",
  unverified: "Annuncio non verificato",
  flagged: "Annuncio segnalato",
};

export default function RecordOverviewTab() {
  const { id = "" } = useParams();
  const overview = useRecordOverview(id);

  if (overview.isLoading) {
    return <div className="h-64 animate-pulse bg-surface-container-low rounded-lg" />;
  }
  if (overview.isError) {
    return <ErrorState error={overview.error} onRetry={() => overview.refetch()} />;
  }
  if (!overview.data) {
    return (
      <p className="text-body-md text-on-surface-variant">Nessun riepilogo disponibile per questo record.</p>
    );
  }

  const record = overview.data;
  const customFieldGroups = record.customFieldGroups ?? [];

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-gutter">
      <div className="xl:col-span-8 space-y-gutter">
        <section className="bg-surface-container-lowest border border-border rounded-lg shadow-sm">
          <div className="p-4 border-b border-border flex justify-between items-center bg-surface-container-lowest">
            <h3 className="text-headline-sm text-on-surface flex items-center gap-2">
              <Icon name="campaign" className="text-outline" />
              Canonical Listing
            </h3>
            <span className="px-2 py-1 bg-surface-container-high text-on-surface-variant rounded text-mono-data font-mono border border-border">
              ID: {record.id}
            </span>
          </div>
          <div className="p-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-6">
              <div className="md:col-span-2">
                <label className="text-label-sm text-on-surface-variant block mb-1">Titolo</label>
                <div className="text-body-lg text-on-surface font-medium">{record.canonicalTitle}</div>
              </div>
              <div className="md:col-span-2">
                <label className="text-label-sm text-on-surface-variant block mb-1">Descrizione</label>
                <div className="whitespace-pre-line text-body-md text-on-surface bg-surface-container-lowest p-4 border border-border rounded leading-relaxed">
                  {record.canonicalDescription}
                </div>
              </div>
              <div>
                <label className="text-label-sm text-on-surface-variant block mb-1">Telefono</label>
                <div className="text-body-md text-on-surface font-mono">{record.phone}</div>
              </div>
              <div>
                <label className="text-label-sm text-on-surface-variant block mb-1">Punteggio di affidabilità</label>
                <div className="flex items-center gap-3">
                  <ProgressBar value={record.confidenceScore} tone="success" className="max-w-[120px]" />
                  <span className="text-body-md font-medium text-success">{record.confidenceScore}%</span>
                </div>
              </div>
              <div>
                <label className="text-label-sm text-on-surface-variant block mb-1">Stato del record</label>
                <Badge tone={STATUS_TONE[record.status] ?? "neutral"}>
                  {STATUS_LABEL[record.status] ?? record.status}
                </Badge>
              </div>
              <div>
                <label className="text-label-sm text-on-surface-variant block mb-1">Ultimo rilevamento</label>
                <div className="flex items-center gap-2 text-body-md text-on-surface">
                  <Icon name="schedule" size={16} className="text-outline" />
                  <span className="font-mono text-sm">{formatDateTime(record.lastSeenAt)}</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {customFieldGroups.some((group) => group.name !== "tags") && (
          <section className="bg-surface-container-lowest border border-border rounded-lg shadow-sm">
            <div className="p-4 border-b border-border">
              <h3 className="text-headline-sm text-on-surface flex items-center gap-2">
                <Icon name="data_object" className="text-outline" />
                Tutti i campi raccolti
              </h3>
            </div>
            <div className="p-6">
              <AggregatedCustomFields groups={customFieldGroups} exclude={["tags"]} />
            </div>
          </section>
        )}
      </div>

      <div className="xl:col-span-4 space-y-gutter">
        <div className="bg-surface-container-lowest border border-border rounded-lg shadow-sm p-5">
          <h3 className="text-headline-sm text-on-surface mb-4">Riepilogo entità</h3>
          <div className="space-y-3">
            <div className="flex items-center gap-3 p-3 border border-border rounded-md">
              <div className="w-8 h-8 rounded bg-primary/10 text-primary flex items-center justify-center">
                <Icon name="call" size={18} />
              </div>
              <div>
                <div className="text-label-sm text-on-surface-variant">Numero di telefono</div>
                <div className="text-body-md font-medium text-on-surface font-mono">{record.phone}</div>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 border border-border rounded-md">
              <div className="w-8 h-8 rounded bg-info/10 text-info flex items-center justify-center">
                <Icon name="public" size={18} />
              </div>
              <div>
                <div className="text-label-sm text-on-surface-variant">Fonti uniche</div>
                <div className="text-body-md font-medium text-on-surface">{record.sourcesCount} fonti</div>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 border border-border rounded-md">
              <div className="w-8 h-8 rounded bg-warning/10 text-warning flex items-center justify-center">
                <Icon name="find_in_page" size={18} />
              </div>
              <div>
                <div className="text-label-sm text-on-surface-variant">Occorrenze</div>
                <div className="text-body-md font-medium text-on-surface">
                  {record.occurrencesCount} Total
                </div>
              </div>
            </div>
          </div>
        </div>

        {record.tags.length > 0 && (
          <div className="bg-surface-container-lowest border border-border rounded-lg shadow-sm p-5">
            <h3 className="text-headline-sm text-on-surface mb-4">Tag</h3>
            <div className="flex flex-wrap gap-2">
              {record.tags.map((tag) => (
                <span
                  key={tag}
                  className="px-2 py-1 bg-surface-container-high text-on-surface-variant rounded text-label-sm"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
