import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as recordsApi from "@/api/records";
import type { RecordSearchFilters } from "@/types";

export function useRecordSearch(filters: RecordSearchFilters) {
  return useQuery({
    queryKey: ["records", "search", filters],
    queryFn: () => recordsApi.searchRecords(filters),
    // A partial phone is held client-side until it can be normalized safely; an
    // empty filter set intentionally loads the complete paginated record list.
    enabled:
      !filters.phone ||
      filters.phone.replace(/\D/g, "").length >= 9 ||
      Boolean(filters.source || filters.status || filters.dateFrom || filters.dateTo),
    placeholderData: (previous) => previous,
  });
}

export function useRecordOverview(id: string) {
  return useQuery({ queryKey: ["records", id, "overview"], queryFn: () => recordsApi.fetchRecordOverview(id), enabled: Boolean(id) });
}

export function useRecordOccurrences(id: string) {
  return useQuery({ queryKey: ["records", id, "occurrences"], queryFn: () => recordsApi.fetchRecordOccurrences(id), enabled: Boolean(id) });
}

export function useOccurrenceDetail(recordId: string, advertisementId: string, enabled = true) {
  return useQuery({
    queryKey: ["records", recordId, "occurrences", advertisementId, "detail"],
    queryFn: () => recordsApi.fetchOccurrenceDetail(recordId, advertisementId),
    enabled: enabled && Boolean(recordId && advertisementId),
  });
}

export function useRecordMedia(id: string) {
  return useQuery({ queryKey: ["records", id, "media"], queryFn: () => recordsApi.fetchRecordMedia(id), enabled: Boolean(id) });
}

export function useOccurrenceVersions(recordId: string, advertisementId: string, enabled = true) {
  return useQuery({
    queryKey: ["records", recordId, "occurrences", advertisementId, "versions"],
    queryFn: () => recordsApi.fetchOccurrenceVersions(recordId, advertisementId),
    enabled: enabled && Boolean(recordId && advertisementId),
  });
}

export function useReviewMedia(recordId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ mediaId, classification, notes }: { mediaId: string; classification: "safe" | "explicit"; notes: string }) =>
      recordsApi.reviewMedia(mediaId, classification, notes),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["records", recordId, "media"] }),
  });
}

export function useReprocessMedia(recordId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (mediaId: string) => recordsApi.reprocessMedia(mediaId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["records", recordId, "media"] }),
  });
}

export function useRecordHistory(id: string) {
  return useQuery({ queryKey: ["records", id, "history"], queryFn: () => recordsApi.fetchRecordHistory(id), enabled: Boolean(id) });
}

export function useRecordAiSummary(id: string) {
  return useQuery({ queryKey: ["records", id, "ai-summary"], queryFn: () => recordsApi.fetchRecordAiSummary(id), enabled: Boolean(id) });
}

export function useRegenerateAiSummary(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      let job = await recordsApi.regenerateRecordAiSummary(id);
      while (job.status === "pending" || job.status === "processing") {
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        job = await recordsApi.fetchSummaryGenerationJob(id, job.id);
      }
      if (job.status === "failed") throw new Error(job.errorMessage ?? "Generazione del riepilogo AI non riuscita.");
      return job;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["records", id, "ai-summary"] });
      queryClient.invalidateQueries({ queryKey: ["records", id, "ai-summary", "versions"] });
    },
  });
}

export function useRecordAiSummaryVersions(id: string) {
  return useQuery({
    queryKey: ["records", id, "ai-summary", "versions"],
    queryFn: () => recordsApi.fetchRecordAiSummaryVersions(id),
    enabled: Boolean(id),
  });
}
