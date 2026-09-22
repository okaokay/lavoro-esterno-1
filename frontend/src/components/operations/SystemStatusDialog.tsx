/** Diagnostica on-demand dei componenti interni, caricata solo a modale aperta. */
import Dialog from "@/components/ui/Dialog";
import { useSystemStatus } from "@/hooks/useOperations";
import { statusLabel } from "@/lib/labels";

export default function SystemStatusDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const system = useSystemStatus(open);

  return (
    <Dialog open={open} onClose={onClose} title="Stato del sistema">
      <div className="space-y-3">
        <div className="flex justify-between">
          <span>Stato complessivo</span>
          <strong>{system.data ? statusLabel(system.data.status) : "Verifica…"}</strong>
        </div>
        {system.isError && <p className="text-error text-sm">Impossibile verificare lo stato dei servizi.</p>}
        {system.data?.components.map((component) => (
          <div key={component.name} className="flex justify-between gap-4 border-t border-border pt-2">
            <div>
              <p className="font-medium">{component.name}</p>
              {component.message && <p className="text-xs text-on-surface-variant">{component.message}</p>}
            </div>
            <div className="text-right">
              <span className="text-sm">{statusLabel(component.status)}</span>
              {component.latencyMs !== null && <p className="text-xs font-mono">{component.latencyMs} ms</p>}
            </div>
          </div>
        ))}
        <button onClick={() => system.refetch()} className="text-sm text-primary">
          Aggiorna stato
        </button>
      </div>
    </Dialog>
  );
}
