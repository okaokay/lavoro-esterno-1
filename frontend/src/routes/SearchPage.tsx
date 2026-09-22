import { useCallback, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useRecordSearch } from "@/hooks/useRecords";
import { useSources } from "@/hooks/useSources";
import Icon from "@/components/ui/Icon";
import Input from "@/components/ui/Input";
import Select from "@/components/ui/Select";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import { EmptyRow, ErrorRow, LoadingRow, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/Table";
import type { RecordSearchFilters, RecordSearchResult } from "@/types";

// Replicates desing/search_lavoro_esterno/code.html: phone search bar,
// advanced filters (source/status/date range), results table and pagination.

const STATUS_TONE: Record<RecordSearchResult["status"], BadgeTone> = {
  verified: "success",
  flagged: "warning",
  unverified: "neutral",
};

const STATUS_LABEL: Record<RecordSearchResult["status"], string> = {
  verified: "Verificato",
  flagged: "Segnalato",
  unverified: "Non verificato",
};

const PAGE_SIZE = 25;

function formatDate(iso: string): string {
  return iso.slice(0, 10);
}

export default function SearchPage() {
  // Filters live in the URL query string (not local state) so a refresh
  // doesn't lose the search and the URL can be shared/bookmarked as-is.
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const phone = searchParams.get("phone") ?? "";
  const source = searchParams.get("source") ?? "";
  const status = searchParams.get("status") ?? "";
  const dateFrom = searchParams.get("dateFrom") ?? "";
  const dateTo = searchParams.get("dateTo") ?? "";
  const page = Math.max(1, Number(searchParams.get("page") ?? "1") || 1);

  // Merges a partial patch into the current query string, dropping empty
  // values entirely rather than keeping them as "key=" — keeps the URL
  // clean. Any filter change also resets `page` unless explicitly overridden.
  const updateParams = useCallback(
    (patch: Record<string, string | number | undefined>, resetPage = true) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          const fullPatch = resetPage ? { ...patch, page: undefined } : patch;
          for (const [key, value] of Object.entries(fullPatch)) {
            if (value === undefined || value === "") next.delete(key);
            else next.set(key, String(value));
          }
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const sources = useSources();

  const filters: RecordSearchFilters = useMemo(
    () => ({
      phone: phone || undefined,
      source: source || undefined,
      status: status || undefined,
      dateFrom: dateFrom || undefined,
      dateTo: dateTo || undefined,
      page,
      pageSize: PAGE_SIZE,
    }),
    [phone, source, status, dateFrom, dateTo, page],
  );

  const search = useRecordSearch(filters);
  // The hook is gated (enabled: only once a filter is set) — mirror that here
  // so we can show a distinct "type something" state before any query has run.
  const phoneReady = !phone || phone.replace(/\D/g, "").length >= 9;

  function clearAll() {
    setSearchParams({}, { replace: true });
  }

  function setPage(updater: (current: number) => number) {
    updateParams({ page: updater(page) }, false);
  }

  const total = search.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const hasFilters = Boolean(phone || source || status || dateFrom || dateTo);
  const filterExportParams = new URLSearchParams({ scope: hasFilters ? "filters" : "all" });
  if (phone) filterExportParams.set("phone", phone);
  if (source) filterExportParams.set("source", source);
  if (status) filterExportParams.set("status", status);
  if (dateFrom) filterExportParams.set("dateFrom", dateFrom);
  if (dateTo) filterExportParams.set("dateTo", dateTo);

  return (
    <div className="space-y-6">
      {/* Records header and filters */}
      <section className="space-y-4">
        <div>
          <h2 className="text-headline-md text-on-surface">Record</h2>
          <p className="text-body-md text-on-surface-variant mt-1">
            Consulta e filtra i record raccolti da tutte le fonti sincronizzate.
          </p>
        </div>
        <div className="max-w-3xl">
          <Input
            icon="search"
              placeholder="es. +39 345 678 9012"
            value={phone}
            onChange={(e) => updateParams({ phone: e.target.value })}
            className="py-4 text-body-lg rounded-xl"
          />
        </div>
      </section>

      {/* Advanced Filters */}
      <section className="bg-surface-container-lowest border border-border rounded-lg p-4 shadow-[0_1px_2px_rgba(0,0,0,0.02)]">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-body-md font-semibold text-on-surface flex items-center gap-2">
            <Icon name="tune" size={18} className="text-primary" />
            Filtri avanzati
          </h3>
          <button onClick={clearAll} className="text-label-sm text-primary hover:text-primary-container transition-colors">
            Azzera tutto
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="space-y-2">
            <label htmlFor="filter-source" className="text-label-sm text-on-surface-variant block">
              Fonte di origine
            </label>
            <Select
              id="filter-source"
              className="w-full"
              value={source}
              onChange={(e) => updateParams({ source: e.target.value })}
            >
              <option value="">Tutte le fonti</option>
              {sources.data?.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-2">
            <label htmlFor="filter-status" className="text-label-sm text-on-surface-variant block">
              Stato di verifica
            </label>
            <Select
              id="filter-status"
              className="w-full"
              value={status}
              onChange={(e) => updateParams({ status: e.target.value })}
            >
              <option value="">Qualsiasi stato</option>
              <option value="verified">Verificato</option>
              <option value="flagged">Segnalato</option>
              <option value="unverified">Non verificato</option>
            </Select>
          </div>
          <div className="space-y-2">
            <span id="filter-last-seen-label" className="text-label-sm text-on-surface-variant block">
              Data ultimo rilevamento
            </span>
            <div className="flex items-center gap-2" role="group" aria-labelledby="filter-last-seen-label">
              <input
                type="date"
                aria-label="Ultimo rilevamento dal"
                value={dateFrom}
                onChange={(e) => updateParams({ dateFrom: e.target.value })}
                className="w-full rounded border border-outline-variant bg-surface text-body-md text-on-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container py-2 px-3 outline-none transition-colors"
              />
              <span className="text-outline" aria-hidden="true">-</span>
              <input
                type="date"
                aria-label="Ultimo rilevamento al"
                value={dateTo}
                onChange={(e) => updateParams({ dateTo: e.target.value })}
                className="w-full rounded border border-outline-variant bg-surface text-body-md text-on-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container py-2 px-3 outline-none transition-colors"
              />
            </div>
          </div>
        </div>
      </section>

      {/* Results */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h3 className="text-headline-sm text-on-surface">Elenco record</h3>
            {search.data && (
              <span className="bg-surface-container-high text-on-surface-variant text-label-sm px-2 py-0.5 rounded-full border border-border">
                {total.toLocaleString("it-IT")} trovati
              </span>
            )}
          </div>
          {phoneReady && search.data && search.data.results.length > 0 && (
            <div className="flex gap-2">
              {selectedIds.size > 0 && (
                <Link
                  to={`/exports?scope=selected&recordIds=${encodeURIComponent([...selectedIds].join(","))}`}
                  className="px-3 py-2 rounded bg-surface-container-high text-label-sm text-on-surface"
                >
                  Esporta selezionati ({selectedIds.size})
                </Link>
              )}
              <Link
                to={`/exports?${filterExportParams.toString()}`}
                className="px-3 py-2 rounded bg-primary text-on-primary text-label-sm"
              >
                {hasFilters ? "Esporta tutti i risultati" : "Esporta tutto l’archivio"}
              </Link>
            </div>
          )}
        </div>

        <div className="bg-surface-container-lowest border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] flex flex-col min-h-[300px]">
          <Table>
            <THead>
              <Tr className="hover:bg-transparent">
                <Th className="text-center">Seleziona</Th>
                <Th>Numero di telefono</Th>
                <Th>Titolo canonico</Th>
                <Th className="text-right">Fonti</Th>
                <Th className="text-right">Occorrenze</Th>
                <Th>Cronologia (prima / ultima)</Th>
                <Th>Stato</Th>
                <Th className="text-center">Azione</Th>
              </Tr>
            </THead>
            <TBody>
              {!phoneReady && (
                <EmptyRow colSpan={8} message="Inserisci almeno 9 cifre per cercare per numero di telefono." />
              )}
              {phoneReady && search.isLoading && <LoadingRow colSpan={8} />}
              {phoneReady && search.isError && (
                <ErrorRow colSpan={8} error={search.error} onRetry={() => search.refetch()} />
              )}
              {phoneReady && search.data && search.data.results.length === 0 && (
                <EmptyRow colSpan={8} message="Nessun record corrisponde ai filtri." />
              )}
              {phoneReady &&
                search.data?.results.map((record) => (
                  <Tr key={record.id}>
                    <Td className="text-center">
                      <input
                        type="checkbox"
                        aria-label={`Seleziona record ${record.id}`}
                        checked={selectedIds.has(record.id)}
                        onChange={(event) => {
                          setSelectedIds((current) => {
                            const next = new Set(current);
                            if (event.target.checked) next.add(record.id);
                            else next.delete(record.id);
                            return next;
                          });
                        }}
                        className="h-4 w-4 accent-primary"
                      />
                    </Td>
                    <Td>
                      <div className="flex items-center gap-2">
                        <Icon name="call" size={16} className="text-outline" />
                        <span className="font-mono text-mono-data font-medium text-on-surface tracking-tight">
                          {record.phone}
                        </span>
                      </div>
                    </Td>
                    <Td className="text-on-surface font-medium truncate max-w-[220px]" title={record.canonicalTitle}>
                      {record.canonicalTitle || <span className="text-outline italic">Nessun titolo trovato</span>}
                    </Td>
                    <Td className="text-right font-mono text-on-surface-variant">{record.sourcesCount}</Td>
                    <Td className="text-right font-mono text-on-surface-variant">{record.occurrencesCount}</Td>
                    <Td>
                      <div className="flex flex-col text-[11px] leading-tight font-mono text-on-surface-variant">
                        <span>{formatDate(record.firstSeenAt)}</span>
                        <span className="text-on-surface font-medium">{formatDate(record.lastSeenAt)}</span>
                      </div>
                    </Td>
                    <Td>
                      <Badge tone={STATUS_TONE[record.status]}>{STATUS_LABEL[record.status]}</Badge>
                    </Td>
                    <Td className="text-center">
                      <Link
                        to={`/exports?scope=selected&recordIds=${record.id}`}
                        className="mr-2 inline-flex p-1 rounded text-on-surface-variant hover:text-primary hover:bg-surface-container-high"
                        title="Esporta questo record"
                      >
                        <Icon name="download" size={18} />
                      </Link>
                      <Link
                        to={`/records/${record.id}`}
                        className="inline-flex p-1 rounded text-on-surface-variant hover:text-primary hover:bg-surface-container-high transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
                      >
                        <Icon name="visibility" size={18} />
                      </Link>
                    </Td>
                  </Tr>
                ))}
            </TBody>
          </Table>

          {phoneReady && search.data && total > 0 && (
            <div className="border-t border-border px-4 py-3 flex items-center justify-between">
              <div className="text-label-sm text-on-surface-variant">
                Risultati da {(page - 1) * PAGE_SIZE + 1} a {Math.min(page * PAGE_SIZE, total)} di {total.toLocaleString("it-IT")}
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="p-1 rounded border border-border text-on-surface-variant disabled:opacity-40 disabled:cursor-not-allowed hover:bg-surface-container-lowest transition-colors"
                >
                  <Icon name="chevron_left" size={16} />
                </button>
                <span className="px-2 text-label-sm text-on-surface-variant">
                  Pagina {page} di {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="p-1 rounded border border-border text-on-surface-variant disabled:opacity-40 disabled:cursor-not-allowed hover:bg-surface-container-lowest transition-colors"
                >
                  <Icon name="chevron_right" size={16} />
                </button>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
