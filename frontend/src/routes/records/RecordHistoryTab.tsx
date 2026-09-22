import { useParams } from "react-router-dom";
import { useRecordHistory } from "@/hooks/useRecords";
import Icon from "@/components/ui/Icon";
import ErrorState from "@/components/ui/ErrorState";
import type { ActivityActor, RecordHistoryEvent } from "@/types";
import { formatDateTime } from "@/lib/format";
import { auditActionLabel } from "@/lib/auditLabels";

// Replicates desing/record_detail_history/code.html: a vertical audit
// timeline, dot-and-line style borrowed from DashboardPage's "Recent
// Activity" panel. The actor->color mapping is intentionally duplicated
// here (rather than imported from DashboardPage, which doesn't export it)
// so this tab stays self-contained and doesn't couple to dashboard internals.

// Canonical-listing changes are the one event type an analyst most needs to
// spot at a glance (they change what "truth" the record shows elsewhere) —
// recognized either by the well-known action label or, more robustly, by the
// `canonical:` id prefix the backend uses for this event type (see
// RecordHistoryEvent's `id` in src/types/index.ts).
function isCanonicalChangeEvent(event: RecordHistoryEvent): boolean {
  return event.id.startsWith("canonical:") || event.action === "Cambio annuncio canonico";
}

function actorDotColor(actor: ActivityActor): string {
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

function actorIcon(actor: ActivityActor): string {
  switch (actor) {
    case "system":
      return "dns";
    case "admin":
      return "admin_panel_settings";
    case "ai":
      return "smart_toy";
    default:
      return "download_for_offline";
  }
}

export default function RecordHistoryTab() {
  const { id = "" } = useParams();
  const history = useRecordHistory(id);

  return (
    <div className="max-w-4xl mx-auto bg-surface-container-lowest border border-border rounded-xl p-8 shadow-sm">
      <h3 className="text-headline-sm text-on-surface flex items-center gap-2 mb-8">
        <Icon name="history" className="text-primary" />
        Registro attività
      </h3>

      {history.isLoading && <p className="text-body-md text-on-surface-variant">Caricamento…</p>}
      {history.isError && <ErrorState error={history.error} onRetry={() => history.refetch()} />}
      {history.data && history.data.length === 0 && (
        <p className="text-body-md text-on-surface-variant">Nessun evento registrato nella cronologia di questo record.</p>
      )}

      {history.data && history.data.length > 0 && (
        <div className="relative space-y-6">
          {history.data.map((event, i) => {
            const isCanonicalChange = isCanonicalChangeEvent(event);
            return (
              <div key={event.id} className="relative pl-12">
                {i !== history.data!.length - 1 && (
                  <div className="absolute left-5 top-10 bottom-[-24px] w-px bg-border" />
                )}
                <div
                  className={
                    isCanonicalChange
                      ? "absolute left-0 top-0 w-10 h-10 rounded-full bg-tertiary/10 border-2 border-tertiary flex items-center justify-center z-10"
                      : "absolute left-0 top-0 w-10 h-10 rounded-full bg-surface-container-low border border-border flex items-center justify-center z-10"
                  }
                >
                  <Icon
                    name={isCanonicalChange ? "swap_horiz" : actorIcon(event.actor)}
                    size={20}
                    className={isCanonicalChange ? "text-tertiary" : actorDotColor(event.actor).replace("bg-", "text-")}
                  />
                </div>
                <div
                  className={
                    isCanonicalChange
                      ? "bg-tertiary/5 border-2 border-tertiary/40 rounded-lg p-4"
                      : "bg-surface-container-lowest border border-border rounded-lg p-4"
                  }
                >
                  <div className="flex justify-between items-start mb-2 gap-4">
                    <div className="flex items-center gap-2">
                      <span className="text-body-md text-on-surface font-semibold">{auditActionLabel(event.action)}</span>
                      <span className="px-2 py-0.5 rounded-full bg-surface-container-high text-on-surface-variant text-[10px] font-mono font-semibold uppercase tracking-wider">
                        {event.actorLabel}
                      </span>
                      {isCanonicalChange && (
                        <span className="px-2 py-0.5 rounded-full bg-tertiary/15 text-tertiary text-[10px] font-mono font-semibold uppercase tracking-wider">
                          Cambio canonico
                        </span>
                      )}
                    </div>
                    <span className="text-mono-data font-mono text-on-surface-variant text-sm whitespace-nowrap">
                      {formatDateTime(event.occurredAt)}
                    </span>
                  </div>
                  <p className="text-body-md text-on-surface-variant">
                    {isCanonicalChange ? (
                      <>
                        <span className="font-medium text-on-surface">Motivo: </span>
                        {event.detail}
                      </>
                    ) : (
                      event.detail
                    )}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
