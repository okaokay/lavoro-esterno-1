import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useDashboardKpis, useRecentActivity, useScrapingActivity, useSourceHealth } from "@/hooks/useDashboard";
import SystemStatusDialog from "@/components/operations/SystemStatusDialog";
import Icon from "@/components/ui/Icon";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import ProgressBar from "@/components/ui/ProgressBar";
import ErrorState from "@/components/ui/ErrorState";
import { EmptyRow, ErrorRow, LoadingRow, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/Table";
import type { ScrapingRunStatus } from "@/types";
import {
  formatRomeDateTime,
  dashboardRangeForRequest,
  resolveDashboardRange,
  toRomeDateTimeInput,
  validateCustomDashboardRange,
  type DashboardRangePreset,
} from "@/lib/dashboardRange";

// Replicates desing/dashboard_lavoro_esterno/code.html: 5 KPI cards with a
// colored top border, a scraping activity table, a source health panel with
// 3 progress bars, and a recent activity timeline.

const STATUS_TONE: Record<ScrapingRunStatus, BadgeTone> = {
  running: "success",
  completed: "success",
  failed: "error",
  rate_limited: "warning",
  queued: "neutral",
};

const STATUS_LABEL: Record<ScrapingRunStatus, string> = {
  running: "In esecuzione",
  completed: "Completata",
  failed: "Non riuscita",
  rate_limited: "Limitata",
  queued: "In coda",
};

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "-";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m >= 60) return `${Math.floor(m / 60)}h ${m % 60}m`;
  return `${m}m ${s}s`;
}

function formatTime(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleTimeString("it-IT", { timeZone: "Europe/Rome", hour: "2-digit", minute: "2-digit" });
}

interface KpiCardConfig {
  key: string;
  label: string;
  icon: string;
  accent: string; // top border + icon color utility
  value: string;
  trend?: { icon: string; label: string; tone: string };
}

export default function DashboardPage() {
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const rangeKey = searchParams.toString();
  const selection = useMemo(
    () => resolveDashboardRange(new URLSearchParams(rangeKey)),
    [rangeKey],
  );
  const [rangeMenuOpen, setRangeMenuOpen] = useState(false);
  const [customStart, setCustomStart] = useState(() =>
    toRomeDateTimeInput(new Date(selection.range.start)),
  );
  const [customEnd, setCustomEnd] = useState(() =>
    toRomeDateTimeInput(new Date(selection.range.end)),
  );
  const [rangeError, setRangeError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const kpis = useDashboardKpis(selection);
  const activity = useScrapingActivity(selection);
  const health = useSourceHealth();
  const recent = useRecentActivity(selection);

  const openRangeMenu = () => {
    const currentRange = dashboardRangeForRequest(selection);
    setCustomStart(toRomeDateTimeInput(new Date(currentRange.start)));
    setCustomEnd(toRomeDateTimeInput(new Date(currentRange.end)));
    setRangeError(null);
    setRangeMenuOpen((open) => !open);
  };

  const selectPreset = (preset: Exclude<DashboardRangePreset, "custom">) => {
    setSearchParams({ range: preset });
    setRangeMenuOpen(false);
    setRefreshError(null);
    setLastUpdatedAt(null);
  };

  const applyCustomRange = () => {
    const result = validateCustomDashboardRange(customStart, customEnd);
    if (!result.range) {
      setRangeError(result.error ?? "Intervallo non valido.");
      return;
    }
    setSearchParams({ range: "custom", start: result.range.start, end: result.range.end });
    setRangeMenuOpen(false);
    setRangeError(null);
    setRefreshError(null);
    setLastUpdatedAt(null);
  };

  const refreshDashboard = async () => {
    setIsRefreshing(true);
    setRefreshError(null);
    try {
      const results = await Promise.all([
        kpis.refetch(),
        activity.refetch(),
        health.refetch(),
        recent.refetch(),
      ]);
      const failed = results.filter((result) => result.isError).length;
      if (failed > 0) {
        setRefreshError(`Impossibile aggiornare ${failed} ${failed === 1 ? "sezione" : "sezioni"} della panoramica.`);
      } else {
        setLastUpdatedAt(new Date());
      }
    } catch {
      setRefreshError("Impossibile aggiornare la panoramica.");
    } finally {
      setIsRefreshing(false);
    }
  };

  const rangeLabel =
    selection.preset === "custom"
      ? `${formatRomeDateTime(selection.range.start)} – ${formatRomeDateTime(selection.range.end)}`
      : { "24h": "Ultime 24 ore", "7d": "Ultimi 7 giorni", "30d": "Ultimi 30 giorni" }[
          selection.preset
        ];

  const cards: KpiCardConfig[] | null = kpis.data
    ? [
        {
          key: "total",
          label: "Record totali",
          icon: "database",
          accent: "bg-primary text-primary",
          value: kpis.data.totalRecords.toLocaleString(),
          trend: { icon: "add", label: `+${kpis.data.newRecordsInRange} nel periodo selezionato`, tone: "text-success" },
        },
        {
          key: "sources",
          label: "Fonti attive",
          icon: "source",
          accent: "bg-info text-info",
          value: kpis.data.activeSources.toLocaleString(),
          trend: { icon: "check_circle", label: `${kpis.data.activeSourcesHealthyPct}% operative`, tone: "text-on-surface-variant" },
        },
        {
          key: "new-today",
          label: "Nuovi record",
          icon: "add_box",
          accent: "bg-success text-success",
          value: kpis.data.newRecordsInRange.toLocaleString(),
          trend: {
            icon: kpis.data.newRecordsDeltaPct >= 0 ? "trending_up" : "trending_down",
            label: `${kpis.data.newRecordsDeltaPct >= 0 ? "+" : ""}${kpis.data.newRecordsDeltaPct}% rispetto al periodo precedente`,
            tone: kpis.data.newRecordsDeltaPct >= 0 ? "text-success" : "text-error",
          },
        },
        {
          key: "errors",
          label: "Errori di acquisizione",
          icon: "warning",
          accent: "bg-error text-error",
          value: kpis.data.scrapingErrors.toLocaleString(),
          trend: { icon: "trending_up", label: `${kpis.data.scrapingErrorsDelta >= 0 ? "+" : ""}${kpis.data.scrapingErrorsDelta} rispetto a ieri`, tone: "text-error" },
        },
        {
          key: "exports",
          label: "Esportazioni attive",
          icon: "sync",
          accent: "bg-warning text-warning",
          value: kpis.data.activeExports.toLocaleString(),
          trend: { icon: "hourglass_empty", label: "In elaborazione…", tone: "text-warning" },
        },
      ]
    : null;

  return (
    <div className="grid grid-cols-12 gap-gutter">
      <div className="col-span-12 mb-2 flex items-end justify-between">
        <div>
          <h2 className="text-headline-md text-on-surface">Panoramica operativa</h2>
          <p className="text-body-md text-on-surface-variant mt-1">Telemetria e metriche di acquisizione aggiornate.</p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <div className="flex gap-2">
          <div className="relative">
          <button
            type="button"
            onClick={openRangeMenu}
            aria-expanded={rangeMenuOpen}
            className="flex items-center gap-1 px-3 py-1.5 border border-border rounded text-label-sm text-on-surface-variant hover:bg-surface-container-low transition-colors bg-surface-container-lowest"
          >
            <Icon name="calendar_today" size={16} />
            {rangeLabel}
            <Icon name={rangeMenuOpen ? "expand_less" : "expand_more"} size={16} />
          </button>
          {rangeMenuOpen && (
            <div className="absolute right-0 top-10 z-30 w-[340px] rounded-lg border border-border bg-surface-container-lowest p-4 shadow-xl">
              <div className="grid grid-cols-3 gap-2">
                {(["24h", "7d", "30d"] as const).map((preset) => (
                  <button
                    type="button"
                    key={preset}
                    onClick={() => selectPreset(preset)}
                    className={`rounded border px-2 py-1.5 text-label-sm ${selection.preset === preset ? "border-primary bg-primary/10 text-primary" : "border-border hover:bg-surface-container-low"}`}
                  >
                    {preset === "24h" ? "24 ore" : preset === "7d" ? "7 giorni" : "30 giorni"}
                  </button>
                ))}
              </div>
              <div className="mt-4 border-t border-border pt-4 space-y-3">
                <p className="text-label-sm font-semibold text-on-surface">Intervallo personalizzato</p>
                <label className="block text-label-sm text-on-surface-variant">
                  Inizio (Europe/Rome)
                  <input
                    type="datetime-local"
                    value={customStart}
                    onChange={(event) => setCustomStart(event.target.value)}
                    className="mt-1 block w-full rounded border border-border bg-surface px-2 py-1.5 text-on-surface"
                  />
                </label>
                <label className="block text-label-sm text-on-surface-variant">
                  Fine (Europe/Rome)
                  <input
                    type="datetime-local"
                    value={customEnd}
                    max={toRomeDateTimeInput(new Date())}
                    onChange={(event) => setCustomEnd(event.target.value)}
                    className="mt-1 block w-full rounded border border-border bg-surface px-2 py-1.5 text-on-surface"
                  />
                </label>
                {rangeError && <p className="text-label-sm text-error" role="alert">{rangeError}</p>}
                <button type="button" onClick={applyCustomRange} className="w-full rounded bg-primary px-3 py-2 text-label-sm text-on-primary hover:bg-primary-container">
                  Applica intervallo
                </button>
              </div>
            </div>
          )}
          </div>
          <button
            type="button"
            onClick={refreshDashboard}
            disabled={isRefreshing}
            className="flex items-center gap-1 px-3 py-1.5 bg-primary text-on-primary rounded text-label-sm hover:bg-primary-container transition-colors shadow-sm"
          >
            <Icon name="refresh" size={16} className={isRefreshing ? "animate-spin" : undefined} />
            {isRefreshing ? "Aggiornamento…" : "Aggiorna dati"}
          </button>
          </div>
          {lastUpdatedAt && (
            <p className="text-label-sm text-on-surface-variant">
              Aggiornato alle {lastUpdatedAt.toLocaleTimeString("it-IT", { timeZone: "Europe/Rome", hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </p>
          )}
        </div>
      </div>

      {(selection.warning || refreshError) && (
        <div className="col-span-12 rounded border border-warning/40 bg-warning/10 px-4 py-2 text-body-md text-on-surface" role="alert">
          {selection.warning ?? refreshError}
        </div>
      )}

      {/* KPI Cards */}
      <div className="col-span-12 grid grid-cols-5 gap-gutter mb-2">
        {kpis.isLoading &&
          Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="bg-surface-container-lowest border border-border rounded-lg p-4 h-[104px] animate-pulse" />
          ))}
        {kpis.isError && (
          <div className="col-span-5 bg-surface-container-lowest border border-border rounded-lg">
            <ErrorState error={kpis.error} onRetry={() => kpis.refetch()} />
          </div>
        )}
        {cards?.map((card) => (
          <div
            key={card.key}
            className="bg-surface-container-lowest border border-border rounded-lg p-4 flex flex-col justify-between shadow-[0_1px_2px_rgba(0,0,0,0.02)] relative overflow-hidden"
          >
            <div className={`absolute top-0 left-0 w-full h-1 opacity-80 ${card.accent.split(" ")[0]}`} />
            <div className="flex justify-between items-start mb-2">
              <span className="text-label-sm text-on-surface-variant uppercase tracking-wider">{card.label}</span>
              <Icon name={card.icon} className={`opacity-50 ${card.accent.split(" ")[1]}`} />
            </div>
            <div>
              <div className="text-headline-lg font-mono text-on-surface">{card.value}</div>
              {card.trend && (
                <div className={`flex items-center gap-1 mt-1 text-label-sm ${card.trend.tone}`}>
                  <Icon name={card.trend.icon} size={14} />
                  <span>{card.trend.label}</span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Scraping Activity */}
      <div className="col-span-8 flex flex-col gap-gutter">
        <div className="bg-surface-container-lowest border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] flex flex-col h-[500px]">
          <div className="px-5 py-4 border-b border-border flex justify-between items-center bg-surface-container-lowest">
            <h3 className="text-headline-sm text-on-surface flex items-center gap-2">
              <Icon name="data_usage" className="text-primary" />
              Attività di acquisizione
            </h3>
          </div>
          <Table>
            <THead>
              <Tr className="hover:bg-transparent">
                <Th className="w-1/4">Fonte</Th>
                <Th>Stato</Th>
                <Th>Avvio</Th>
                <Th className="text-right">Durata</Th>
                <Th className="text-right">Elementi</Th>
                <Th className="text-right">Errori</Th>
              </Tr>
            </THead>
            <TBody>
              {activity.isLoading && <LoadingRow colSpan={6} />}
              {activity.isError && <ErrorRow colSpan={6} error={activity.error} onRetry={() => activity.refetch()} />}
              {activity.data && activity.data.length === 0 && <EmptyRow colSpan={6} message="Nessuna acquisizione presente." />}
              {activity.data?.map((run) => (
                <Tr key={run.id}>
                  <Td>
                    <div className="font-medium text-on-surface">{run.sourceName}</div>
                    <div className="text-label-sm text-on-surface-variant font-mono">{run.sourceCode}</div>
                  </Td>
                  <Td>
                    <Badge tone={STATUS_TONE[run.status]}>{STATUS_LABEL[run.status]}</Badge>
                  </Td>
                  <Td className="text-on-surface-variant">{formatTime(run.startedAt)}</Td>
                  <Td className="text-right font-mono">{formatDuration(run.durationSeconds)}</Td>
                  <Td className="text-right font-mono text-on-surface">{run.items?.toLocaleString() ?? "-"}</Td>
                  <Td className={`text-right font-mono ${run.errors ? "font-semibold text-error" : "text-on-surface-variant"}`}>
                    {run.errors ?? "-"}
                  </Td>
                </Tr>
              ))}
            </TBody>
          </Table>
        </div>
      </div>

      {/* Right column */}
      <div className="col-span-4 flex flex-col gap-gutter">
        <div className="bg-surface-container-lowest border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] p-5">
          <h3 className="text-headline-sm text-on-surface mb-4 flex items-center gap-2">
            <Icon name="monitor_heart" className="text-info" />
            Stato delle fonti
          </h3>
          {health.isLoading && <p className="text-body-md text-on-surface-variant">Caricamento…</p>}
          {health.isError && <ErrorState error={health.error} onRetry={() => health.refetch()} className="py-4" />}
          {health.data && (
            <div className="space-y-4">
              <HealthRow label="Operative" value={health.data.healthy} total={health.data.total} tone="success" />
              <HealthRow label="Limitate" value={health.data.rateLimited} total={health.data.total} tone="warning" />
              <HealthRow label="In errore" value={health.data.error} total={health.data.total} tone="error" />
            </div>
          )}
          <button
            onClick={() => setDiagnosticsOpen(true)}
            className="w-full mt-5 py-2 border border-border rounded text-label-sm text-on-surface hover:bg-surface-container-lowest transition-colors flex items-center justify-center gap-2"
          >
            Visualizza diagnostica dettagliata
            <Icon name="arrow_forward" size={16} />
          </button>
        </div>

        <div className="bg-surface-container-lowest border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] flex-1 flex flex-col min-h-[300px]">
          <div className="px-5 py-4 border-b border-border bg-surface-container-lowest">
            <h3 className="text-headline-sm text-on-surface flex items-center gap-2">
              <Icon name="history" className="text-outline" />
              Attività recente
            </h3>
          </div>
          <div className="p-5 overflow-y-auto flex-1 space-y-5">
            {recent.isLoading && <p className="text-body-md text-on-surface-variant">Caricamento…</p>}
            {recent.isError && <ErrorState error={recent.error} onRetry={() => recent.refetch()} className="py-4" />}
            {recent.data && recent.data.length === 0 && (
              <p className="text-body-md text-on-surface-variant">Nessuna attività recente.</p>
            )}
            {recent.data?.map((event, i) => (
              <div key={event.id} className="relative pl-6">
                {i !== recent.data!.length - 1 && (
                  <div className="absolute left-1.5 top-1.5 bottom-[-24px] w-px bg-border" />
                )}
                <div
                  className={`absolute left-0 top-1.5 w-3 h-3 rounded-full border-2 border-white shadow-sm ${actorDotColor(event.actor)}`}
                />
                <p className="text-label-sm text-on-surface-variant mb-0.5">{formatTime(event.occurredAt)}</p>
                <p className="text-body-md text-on-surface">
                  <span className="font-semibold">{event.actorLabel}</span> {event.message}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
      <SystemStatusDialog open={diagnosticsOpen} onClose={() => setDiagnosticsOpen(false)} />
    </div>
  );
}

function HealthRow({ label, value, total, tone }: { label: string; value: number; total: number; tone: "success" | "warning" | "error" }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  const toneText = { success: "text-success", warning: "text-warning", error: "text-error" }[tone];
  return (
    <div>
      <div className="flex justify-between items-end mb-1">
        <span className="text-body-md font-medium text-on-surface">{label}</span>
        <span className={`text-label-sm font-mono ${toneText}`}>
          {value} / {total}
        </span>
      </div>
      <ProgressBar value={pct} tone={tone} />
    </div>
  );
}

function actorDotColor(actor: string): string {
  switch (actor) {
    case "system":
      return "bg-primary";
    case "admin":
      return "bg-tertiary";
    case "ai":
      return "bg-info";
    default:
      return "bg-success";
  }
}
