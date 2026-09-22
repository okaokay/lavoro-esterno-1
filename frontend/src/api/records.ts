import { apiRequest } from "./client";
import type {
  RecordAiSummary,
  RecordAiSummaryVersion,
  RecordHistoryEvent,
  RecordMedia,
  RecordOccurrence,
  RecordOccurrenceDetail,
  RecordOverview,
  RecordSearchFilters,
  RecordSearchResponse,
  SummaryGenerationJob,
  AdvertisementVersion,
} from "@/types";

function toQueryString(filters: RecordSearchFilters): string {
  const params = new URLSearchParams();
  if (filters.phone) params.set("phone", filters.phone);
  if (filters.source) params.set("source", filters.source);
  if (filters.status) params.set("status", filters.status);
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  params.set("page", String(filters.page ?? 1));
  params.set("page_size", String(filters.pageSize ?? 25));
  return params.toString();
}

export function searchRecords(filters: RecordSearchFilters): Promise<RecordSearchResponse> {
  return apiRequest<RecordSearchResponse>(`/records/search?${toQueryString(filters)}`);
}

export function fetchRecordOverview(id: string): Promise<RecordOverview> {
  return apiRequest<RecordOverview>(`/records/${id}`);
}

export function fetchRecordOccurrences(id: string): Promise<RecordOccurrence[]> {
  return apiRequest<RecordOccurrence[]>(`/records/${id}/occurrences`);
}

export function fetchOccurrenceDetail(recordId: string, advertisementId: string): Promise<RecordOccurrenceDetail> {
  return apiRequest<RecordOccurrenceDetail>(`/records/${recordId}/occurrences/${advertisementId}`);
}

export function fetchRecordMedia(id: string): Promise<RecordMedia[]> {
  return apiRequest<RecordMedia[]>(`/records/${id}/media`);
}

export function fetchRecordHistory(id: string): Promise<RecordHistoryEvent[]> {
  return apiRequest<RecordHistoryEvent[]>(`/records/${id}/history`);
}

export async function fetchRecordAiSummary(id: string): Promise<RecordAiSummary | null> {
  return (await apiRequest<RecordAiSummary | undefined>(`/records/${id}/ai-summary`)) ?? null;
}

export function fetchOccurrenceVersions(
  recordId: string,
  advertisementId: string,
): Promise<AdvertisementVersion[]> {
  return apiRequest<AdvertisementVersion[]>(
    `/records/${recordId}/occurrences/${advertisementId}/versions`,
  );
}

// Full version history, most recent first — lets the UI offer a version
// picker instead of only ever showing the latest summary.
export function fetchRecordAiSummaryVersions(id: string): Promise<RecordAiSummaryVersion[]> {
  return apiRequest<RecordAiSummaryVersion[]>(`/records/${id}/ai-summary/versions`);
}

// Triggers a fresh AI summary generation job; the summary query should be
// invalidated/refetched by the caller once this resolves.
export function regenerateRecordAiSummary(id: string): Promise<SummaryGenerationJob> {
  return apiRequest<SummaryGenerationJob>(`/records/${id}/ai-summary/regenerate`, { method: "POST" });
}

export function fetchSummaryGenerationJob(id: string, jobId: string): Promise<SummaryGenerationJob> {
  return apiRequest<SummaryGenerationJob>(`/records/${id}/ai-summary/jobs/${jobId}`);
}

export function reviewMedia(mediaId: string, classification: "safe" | "explicit", notes: string): Promise<unknown> {
  return apiRequest(`/media/${mediaId}/review`, { method: "POST", body: { classification, notes } });
}

export function reprocessMedia(mediaId: string): Promise<unknown> {
  return apiRequest(`/media/${mediaId}/reprocess`, { method: "POST" });
}
