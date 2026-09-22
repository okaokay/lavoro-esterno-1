import { Outlet, useParams } from "react-router-dom";
import { useRecordOverview } from "@/hooks/useRecords";
import Icon from "@/components/ui/Icon";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import ProgressBar from "@/components/ui/ProgressBar";
import Tabs, { type TabItem } from "@/components/ui/Tabs";
import { formatDate } from "@/lib/format";

// Replicates desing/record_detail_overview/code.html: a record header (phone,
// status, confidence, counts, dates) shared across all 5 tabs, followed by a
// router-driven tab strip. Each tab route fetches its own data independently,
// so a failure here only degrades the header, not the whole page.

const STATUS_TONE: Record<string, BadgeTone> = {
  verified: "success",
  unverified: "warning",
  flagged: "error",
};

const STATUS_LABEL: Record<string, string> = {
  verified: "Attivo",
  unverified: "Non verificato",
  flagged: "Segnalato",
};

const TAB_ITEMS: TabItem[] = [
  { to: "overview", label: "Riepilogo", icon: "visibility" },
  { to: "occurrences", label: "Occorrenze", icon: "list_alt" },
  { to: "media", label: "Media", icon: "perm_media" },
  { to: "ai-summary", label: "Riepilogo AI", icon: "auto_awesome" },
  { to: "history", label: "Cronologia", icon: "history" },
];

export default function RecordDetailLayout() {
  const { id = "" } = useParams();
  const overview = useRecordOverview(id);

  return (
    <div className="flex flex-col h-full">
      <div className="px-margin-page pt-margin-page pb-0 bg-surface-container-lowest border-b border-border">
        {overview.isLoading && <div className="h-20 mb-6 animate-pulse bg-surface-container-low rounded" />}
        {overview.isError && (
          <div className="mb-6 text-body-md text-error">Impossibile caricare l’intestazione del record.</div>
        )}
        {overview.data && (
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 mb-6">
            <div>
              <div className="flex items-center gap-3 mb-1">
                <h2 className="text-headline-lg text-on-surface font-mono">{overview.data.phone}</h2>
                <Badge tone={STATUS_TONE[overview.data.status] ?? "neutral"}>
                  {STATUS_LABEL[overview.data.status] ?? overview.data.status}
                </Badge>
              </div>
              <p className="text-body-lg text-on-surface font-medium mb-2">{overview.data.canonicalTitle}</p>
              <div className="flex flex-wrap items-center gap-4 text-body-md text-on-surface-variant">
                <span className="flex items-center gap-1.5">
                  <Icon name="find_in_page" size={18} />
                  {overview.data.occurrencesCount} occorrenze
                </span>
                <span className="w-1 h-1 rounded-full bg-outline-variant" />
                <span className="flex items-center gap-1.5">
                  <Icon name="source" size={18} />
                  {overview.data.sourcesCount} fonti
                </span>
                <span className="w-1 h-1 rounded-full bg-outline-variant" />
                <span className="flex items-center gap-1.5">
                  <Icon name="calendar_today" size={18} />
                  Prima rilevazione: {formatDate(overview.data.firstSeenAt)}
                </span>
                <span className="w-1 h-1 rounded-full bg-outline-variant" />
                <span className="flex items-center gap-1.5">
                  <Icon name="update" size={18} />
                  Ultima rilevazione: {formatDate(overview.data.lastSeenAt)}
                </span>
              </div>
              {overview.data.tags.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-3">
                  {overview.data.tags.map((tag) => (
                    <span key={tag} className="px-2 py-1 bg-surface-container-high text-on-surface-variant rounded text-label-sm">
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="flex flex-col items-end gap-2 shrink-0">
              <span className="text-label-sm text-on-surface-variant">Punteggio di affidabilità</span>
              <div className="flex items-center gap-3 w-40">
                <ProgressBar value={overview.data.confidenceScore} tone="success" />
                <span className="text-body-md font-medium text-success">{overview.data.confidenceScore}%</span>
              </div>
            </div>
          </div>
        )}
        <Tabs items={TAB_ITEMS} />
      </div>
      <div className="flex-1 overflow-y-auto p-margin-page bg-surface">
        <Outlet />
      </div>
    </div>
  );
}
