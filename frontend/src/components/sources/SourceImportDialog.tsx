import { useState, type ChangeEvent } from "react";
import Button from "@/components/ui/Button";
import Dialog from "@/components/ui/Dialog";
import Icon from "@/components/ui/Icon";
import Select from "@/components/ui/Select";
import { useImportSources, usePreviewSourcesImport } from "@/hooks/useSources";
import { describeError } from "@/lib/errors";
import type {
  SourceImportPreviewResult,
  SourceImportResult,
  SourceTransferDocument,
} from "@/types";

type ConflictAction = "" | "update" | "skip";

export default function SourceImportDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const previewImport = usePreviewSourcesImport();
  const applyImport = useImportSources();
  const [document, setDocument] = useState<unknown>(null);
  const [preview, setPreview] = useState<SourceImportPreviewResult | null>(null);
  const [actions, setActions] = useState<Record<string, ConflictAction>>({});
  const [fileError, setFileError] = useState<string | null>(null);
  const [result, setResult] = useState<SourceImportResult | null>(null);

  function handleClose() {
    setDocument(null);
    setPreview(null);
    setActions({});
    setFileError(null);
    setResult(null);
    previewImport.reset();
    applyImport.reset();
    onClose();
  }

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    setDocument(null);
    setPreview(null);
    setActions({});
    setResult(null);
    setFileError(null);
    if (!file) return;
    try {
      const parsed: unknown = JSON.parse(await file.text());
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("Il contenuto deve essere un oggetto JSON.");
      }
      const nextPreview = await previewImport.mutateAsync(parsed);
      setDocument(parsed);
      setPreview(nextPreview);
    } catch (error) {
      setFileError(error instanceof SyntaxError ? "Il file non contiene JSON valido." : describeError(error).description);
    }
  }

  const conflicts = preview?.entries.filter((entry) => entry.status === "conflict") ?? [];
  const unresolvedConflicts = conflicts.some((entry) => !entry.slug || !actions[entry.slug]);
  const canApply = Boolean(document && preview?.valid && !unresolvedConflicts && !applyImport.isPending);

  async function handleApply() {
    if (!canApply || !document) return;
    const conflictActions = Object.fromEntries(
      Object.entries(actions).filter((entry): entry is [string, "update" | "skip"] => entry[1] !== ""),
    );
    const imported = await applyImport.mutateAsync({
      document: document as SourceTransferDocument,
      conflictActions,
    });
    setResult(imported);
  }

  return (
    <Dialog open={open} onClose={handleClose} title="Importa fonti" size="xl">
      <div className="space-y-4 max-h-[75vh] overflow-y-auto pr-1">
        {!result && (
          <label className="block">
            <span className="block text-label-sm text-on-surface-variant mb-1">File configurazione JSON</span>
            <input
              type="file"
              accept="application/json,.json"
              onChange={handleFile}
              disabled={previewImport.isPending || applyImport.isPending}
              className="block w-full text-body-md text-on-surface file:mr-3 file:border file:border-border file:bg-surface-container-lowest file:px-3 file:py-2 file:text-label-sm file:text-on-surface hover:file:bg-surface-container-low"
            />
          </label>
        )}

        {previewImport.isPending && <p className="text-body-md text-on-surface-variant">Validazione del file...</p>}
        {(fileError || previewImport.isError || applyImport.isError) && (
          <div role="alert" className="border border-error/20 bg-error-container/20 p-3 text-body-md text-error rounded">
            {fileError ?? describeError(previewImport.error ?? applyImport.error).description}
          </div>
        )}

        {preview && !result && (
          <>
            {preview.globalErrors.length > 0 && (
              <ul className="border border-error/20 bg-error-container/20 p-3 text-body-md text-error rounded">
                {preview.globalErrors.map((error) => <li key={error}>{error}</li>)}
              </ul>
            )}
            <div className="border border-border rounded overflow-x-auto">
              <table className="w-full text-left text-body-md">
                <thead className="bg-surface-container-low text-label-sm text-on-surface-variant">
                  <tr>
                    <th className="px-3 py-2">Fonte</th>
                    <th className="px-3 py-2">Stato</th>
                    <th className="px-3 py-2">Pool proxy</th>
                    <th className="px-3 py-2">Azione</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {preview.entries.map((entry) => (
                    <tr key={entry.index}>
                      <td className="px-3 py-2">
                        <div className="font-medium text-on-surface">{entry.name ?? `Elemento ${entry.index + 1}`}</div>
                        <div className="font-mono text-label-sm text-on-surface-variant">{entry.slug ?? "slug non valido"}</div>
                        {entry.errors.map((message) => (
                          <div key={message} className="mt-1 text-label-sm text-error">{message}</div>
                        ))}
                        {entry.warnings.map((message) => (
                          <div key={message} className="mt-1 text-label-sm text-warning">{message}</div>
                        ))}
                      </td>
                      <td className="px-3 py-2 text-on-surface-variant">
                        {entry.status === "new" ? "Nuova" : entry.status === "conflict" ? "Già presente" : "Non valida"}
                      </td>
                      <td className="px-3 py-2 text-on-surface-variant">
                        {entry.proxyPoolName ?? "Nessuno"}
                      </td>
                      <td className="px-3 py-2">
                        {entry.status === "conflict" ? (
                          <Select
                            aria-label={`Azione per ${entry.slug}`}
                            value={entry.slug ? actions[entry.slug] ?? "" : ""}
                            onChange={(event) => entry.slug && setActions((current) => ({
                              ...current,
                              [entry.slug!]: event.target.value as ConflictAction,
                            }))}
                          >
                            <option value="">Scegli...</option>
                            <option value="update">Aggiorna</option>
                            <option value="skip">Salta</option>
                          </Select>
                        ) : entry.status === "new" ? "Crea disattivata" : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {result && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-success">
              <Icon name="check_circle" />
              <span className="font-medium">Import completato</span>
            </div>
            <p className="text-body-md text-on-surface">
              Create: {result.created}. Aggiornate: {result.updated}. Saltate: {result.skipped}.
            </p>
            {result.warnings.map((warning) => <p key={warning} className="text-body-md text-warning">{warning}</p>)}
          </div>
        )}

        <div className="flex justify-end gap-2 border-t border-border pt-4">
          <Button type="button" variant="secondary" onClick={handleClose}>{result ? "Chiudi" : "Annulla"}</Button>
          {!result && (
            <Button type="button" onClick={handleApply} disabled={!canApply}>
              {applyImport.isPending ? "Importazione..." : "Importa"}
            </Button>
          )}
        </div>
      </div>
    </Dialog>
  );
}
