import { Fragment, useState } from "react";
import { useParams } from "react-router-dom";
import { useOccurrenceDetail, useOccurrenceVersions, useRecordOccurrences } from "@/hooks/useRecords";
import Icon from "@/components/ui/Icon";
import ProgressBar from "@/components/ui/ProgressBar";
import { EmptyRow, ErrorRow, LoadingRow, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/Table";
import CustomFields from "@/components/records/CustomFields";
import { formatDateTime } from "@/lib/format";
import type { CustomFields as CustomFieldsMap } from "@/types";

// Replicates desing/record_detail_occurrences/code.html: every scraped
// occurrence that was merged into this record, with the canonical one
// (the source picked as "truth" for the merged fields) tinted primary/10
// and tagged "Canonical" — a positive highlight, unlike the error-tinted
// rows used elsewhere in the app for offline sources.

function OccurrenceDetails({
  recordId,
  occurrenceId,
  customFields,
}: {
  recordId: string;
  occurrenceId: string;
  customFields: CustomFieldsMap;
}) {
  const versions = useOccurrenceVersions(recordId, occurrenceId);
  const detail = useOccurrenceDetail(recordId, occurrenceId);
  return (
    <div className="space-y-5">
      {detail.isLoading && <p className="text-body-sm text-on-surface-variant">Caricamento riepilogo…</p>}
      {detail.data && (
        <div className="grid gap-4 md:grid-cols-2">
          <section className="rounded border border-border bg-surface-container-lowest p-4">
            <h4 className="font-semibold text-on-surface">{detail.data.title}</h4>
            <p className="mt-2 whitespace-pre-wrap text-body-sm text-on-surface-variant">{detail.data.description || "Nessuna descrizione"}</p>
          </section>
          <section className="rounded border border-border bg-surface-container-lowest p-4 text-body-sm">
            <div><strong>Telefono:</strong> {detail.data.phone}</div>
            <div><strong>Paese:</strong> {detail.data.countryCode ?? "N/D"}</div>
            <div><strong>Pagina listing:</strong> {detail.data.listingPageNumber ?? "Sconosciuta"}</div>
            <div><strong>Stato:</strong> {detail.data.status}</div>
            <div><strong>Prima acquisizione:</strong> {formatDateTime(detail.data.firstSeenAt)}</div>
            <div><strong>Ultimo rilevamento:</strong> {formatDateTime(detail.data.lastSeenAt)}</div>
          </section>
          {detail.data.media.length > 0 && (
            <section className="md:col-span-2">
              <h4 className="mb-2 font-semibold">Media ({detail.data.media.length})</h4>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                {detail.data.media.map((item) => <img key={item.id} src={item.thumbnailUrl} alt="" className="h-32 w-full rounded object-cover" />)}
              </div>
            </section>
          )}
        </div>
      )}
      {Object.keys(detail.data?.customFields ?? customFields).length > 0 && <CustomFields fields={detail.data?.customFields ?? customFields} compact />}
      <div>
        <h4 className="mb-2 text-label-md font-semibold text-on-surface">Cronologia versioni</h4>
        {versions.isLoading && <p className="text-body-sm text-on-surface-variant">Caricamento versioni…</p>}
        {versions.isError && <p className="text-body-sm text-error">Impossibile caricare la cronologia versioni.</p>}
        <div className="space-y-2">
          {versions.data?.map((version, index) => {
            const previous = versions.data[index + 1];
            return (
              <div key={version.id} className="rounded border border-border bg-surface-container-lowest p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-semibold">Revisione {version.revision}</span>
                  <span className="font-mono text-label-sm text-on-surface-variant">{formatDateTime(version.createdAt)}</span>
                </div>
                <p className="mt-1 text-body-sm text-on-surface-variant">
                  {version.changedFields.length ? `Campi modificati: ${version.changedFields.join(", ")}` : "Snapshot iniziale"}
                </p>
                {previous && (
                  <p className="mt-1 text-label-sm text-on-surface-variant">
                    Confrontata con la revisione {previous.revision}; media correnti: {version.snapshot.mediaHashes?.length ?? 0}.
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default function RecordOccurrencesTab() {
  const { id = "" } = useParams();
  const occurrences = useRecordOccurrences(id);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  const toggleExpanded = (occurrenceId: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(occurrenceId)) next.delete(occurrenceId);
      else next.add(occurrenceId);
      return next;
    });
  };

  return (
    <div className="bg-surface-container-lowest border border-border rounded-lg shadow-sm flex flex-col">
      <div className="p-4 border-b border-border flex justify-between items-center bg-surface-container-lowest rounded-t-lg">
        <span className="text-label-sm text-on-surface font-semibold">
          {occurrences.data ? `${occurrences.data.length} occorrenze trovate` : "Occorrenze"}
        </span>
      </div>
      <Table>
        <THead>
          <Tr className="hover:bg-transparent">
            <Th>Fonte</Th>
            <Th>Titolo</Th>
            <Th>URL sorgente</Th>
            <Th>Data acquisizione</Th>
            <Th>Affidabilità corrispondenza</Th>
            <Th>
              <span className="sr-only">Campi personalizzati</span>
            </Th>
          </Tr>
        </THead>
        <TBody>
          {occurrences.isLoading && <LoadingRow colSpan={6} />}
          {occurrences.isError && (
            <ErrorRow colSpan={6} error={occurrences.error} onRetry={() => occurrences.refetch()} />
          )}
          {occurrences.data && occurrences.data.length === 0 && (
            <EmptyRow colSpan={6} message="Nessuna occorrenza trovata per questo record." />
          )}
          {occurrences.data?.map((occ) => {
            const customFields = occ.customFields ?? {};
            const isExpanded = expanded.has(occ.id);
            return (
              <Fragment key={occ.id}>
                <Tr className={occ.isCanonical ? "bg-primary/5" : undefined}>
                  <Td>
                    <div className="flex items-center gap-2">
                      <div className="w-6 h-6 rounded bg-surface-container flex items-center justify-center text-primary shrink-0">
                        <Icon name="public" size={14} />
                      </div>
                      <div>
                        <div className="font-medium text-on-surface">{occ.sourceName}</div>
                        <div className="text-label-sm text-on-surface-variant font-mono">
                          {occ.sourceCode}
                        </div>
                      </div>
                    </div>
                  </Td>
                  <Td>
                    <div className="flex items-center gap-2">
                      <span className="text-on-surface truncate max-w-[220px] inline-block">{occ.title}</span>
                      {occ.isCanonical && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase bg-primary-container text-on-primary border border-primary/20">
                          Canonical
                        </span>
                      )}
                      {occ.hasUpdates && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase bg-info/10 text-info border border-info/30">
                          Aggiornata · r{occ.revision}
                        </span>
                      )}
                    </div>
                  </Td>
                  <Td>
                    <a
                      href={occ.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-mono-data font-mono text-primary hover:underline truncate max-w-[200px] inline-block"
                    >
                      {occ.url}
                    </a>
                  </Td>
                  <Td className="text-on-surface-variant">
                    <div className="font-mono text-sm">{formatDateTime(occ.scrapedAt)}</div>
                    <div className="text-label-sm">Ultima modifica: {formatDateTime(occ.lastChangedAt)}</div>
                  </Td>
                  <Td>
                    <div className="flex items-center gap-2">
                      <ProgressBar
                        value={occ.matchConfidence}
                        tone={
                          occ.matchConfidence >= 80
                            ? "success"
                            : occ.matchConfidence >= 60
                              ? "warning"
                              : "error"
                        }
                        className="w-16"
                      />
                      <span className="text-label-sm text-on-surface">{occ.matchConfidence}%</span>
                    </div>
                  </Td>
                  <Td className="text-right">
                    <button
                      type="button"
                      aria-expanded={isExpanded}
                      aria-label={`${isExpanded ? "Nascondi" : "Mostra"} campi personalizzati per ${occ.title}`}
                      onClick={() => toggleExpanded(occ.id)}
                      className="inline-flex items-center gap-1 rounded px-2 py-1 text-label-sm text-primary hover:bg-primary/10"
                    >
                      <Icon name={isExpanded ? "expand_less" : "expand_more"} size={18} />
                      Details
                    </button>
                  </Td>
                </Tr>
                {isExpanded && (
                  <Tr className={occ.isCanonical ? "bg-primary/5" : "bg-surface-container-low"}>
                    <Td colSpan={6} className="px-8 py-5">
                      <OccurrenceDetails
                        recordId={id}
                        occurrenceId={occ.id}
                        customFields={customFields}
                      />
                    </Td>
                  </Tr>
                )}
              </Fragment>
            );
          })}
        </TBody>
      </Table>
    </div>
  );
}
