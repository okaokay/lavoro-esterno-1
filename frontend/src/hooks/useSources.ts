import { useMutation, useQuery, useQueryClient, type Query } from "@tanstack/react-query";
import * as sourcesApi from "@/api/sources";
import type { ScrapeConfig, ScrapeRun } from "@/types";

const sourcesKey = ["sources"] as const;
const summaryKey = ["sources", "summary"] as const;

const ACTIVE_POLL_INTERVAL_MS = 3000;

export function useSources() {
  return useQuery({ queryKey: sourcesKey, queryFn: sourcesApi.fetchSources, refetchInterval: 30000 });
}

export function useSourcesSummary() {
  return useQuery({ queryKey: summaryKey, queryFn: sourcesApi.fetchSourcesSummary });
}

export function useExportSources() {
  return useMutation({ mutationFn: sourcesApi.exportSources });
}

export function usePreviewSourcesImport() {
  return useMutation({ mutationFn: sourcesApi.previewSourcesImport });
}

export function useImportSources() {
  const invalidate = useInvalidateSources();
  return useMutation({ mutationFn: sourcesApi.importSources, onSuccess: invalidate });
}

// Shared invalidation for the three source action mutations below — any of
// them can change status/health, so refresh both the list and the summary cards.
function useInvalidateSources() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: sourcesKey });
    queryClient.invalidateQueries({ queryKey: summaryKey });
  };
}

export function useRunSourceScan() {
  const invalidate = useInvalidateSources();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: sourcesApi.runSourceScan,
    onSuccess: (_data, sourceId) => {
      invalidate();
      // The runs panel may already be mounted (row expanded) or not — either
      // way, invalidate so it picks up the just-queued run as soon as it's
      // visible, instead of only refreshing on the next manual expand.
      queryClient.invalidateQueries({ queryKey: ["sources", sourceId, "runs"] });
    },
  });
}

export function usePauseSource() {
  const invalidate = useInvalidateSources();
  return useMutation({ mutationFn: sourcesApi.pauseSource, onSuccess: invalidate });
}

export function useDisableSource() {
  const invalidate = useInvalidateSources();
  return useMutation({ mutationFn: sourcesApi.disableSource, onSuccess: invalidate });
}

export function useEnableSource() {
  const invalidate = useInvalidateSources();
  return useMutation({ mutationFn: sourcesApi.enableSource, onSuccess: invalidate });
}

export function useDuplicateSource() {
  const invalidate = useInvalidateSources();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: sourcesApi.DuplicateSourceInput }) =>
      sourcesApi.duplicateSource(id, input),
    onSuccess: invalidate,
  });
}

// Only fetched when a row is actually expanded (`enabled`) — no point
// loading run history for every source up front.
export function useSourceRuns(id: string, enabled: boolean) {
  // Poll while the most recent run is still "running" so status/results show
  // up without a manual refresh — same pattern as useExportJobs. Stops as
  // soon as every visible run has settled to "completed"/"failed".
  return useQuery({
    queryKey: ["sources", id, "runs"],
    queryFn: () => sourcesApi.fetchSourceRuns(id),
    enabled,
    refetchInterval: (query: Query<ScrapeRun[]>) => {
      const runs = query.state.data;
      const hasActiveRun = runs?.some((run) => run.status === "pending" || run.status === "running");
      return hasActiveRun ? ACTIVE_POLL_INTERVAL_MS : false;
    },
  });
}

// Only fetched when the "Edit configuration" dialog is actually open
// (`enabled`) — the plain list view never needs the full scrapeConfig.
export function useSource(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ["sources", id],
    queryFn: () => sourcesApi.fetchSource(id),
    enabled,
  });
}

export function useCreateSource() {
  const invalidate = useInvalidateSources();
  return useMutation({ mutationFn: sourcesApi.createSource, onSuccess: invalidate });
}

export function useUpdateSource() {
  const invalidate = useInvalidateSources();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: sourcesApi.UpdateSourceInput }) =>
      sourcesApi.updateSource(id, input),
    onSuccess: invalidate,
  });
}

export function useDeleteSource() {
  const invalidate = useInvalidateSources();
  return useMutation({ mutationFn: sourcesApi.deleteSource, onSuccess: invalidate });
}

// Not a mutation in the TanStack sense (nothing is persisted server-side),
// but modeled as one anyway: it's a real network call with a loading/error
// lifecycle the UI needs to reflect (a disabled button + spinner while
// checking), which is exactly what useMutation is for.
export function useCheckSourceRobots() {
  return useMutation({ mutationFn: sourcesApi.checkSourceRobots });
}

export function useTestSourceConfig() {
  return useMutation({
    mutationFn: ({ id, scrapeConfig, proxyPoolId }: {
      id: string;
      scrapeConfig: ScrapeConfig;
      proxyPoolId: string | null;
    }) => sourcesApi.testSourceConfig(id, scrapeConfig, proxyPoolId),
  });
}

export function useUpdateSourceSchedule() {
  const invalidate = useInvalidateSources();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: sourcesApi.SourceScheduleInput }) =>
      sourcesApi.updateSourceSchedule(id, input),
    onSuccess: invalidate,
  });
}
