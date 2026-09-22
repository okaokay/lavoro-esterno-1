import { apiRequest } from "./client";
import type {
  RobotsCheckResult,
  ScrapeConfig,
  ScrapeIntervalUnit,
  ScrapeRun,
  Source,
  SourceImportPreviewResult,
  SourceImportResult,
  SourcePriority,
  SourceTransferDocument,
  TestConfigResult,
  WatermarkRemovalConfig,
} from "@/types";

export interface SourcesSummary {
  total: number;
  active: number;
  degraded: number;
  offline: number;
}

export interface SourceDetail extends Source {
  scrapeConfig: ScrapeConfig | null;
  watermarkRemoval: WatermarkRemovalConfig;
}

export interface CreateSourceInput {
  name: string;
  slug: string;
  baseUrl: string;
  countryCode?: string | null;
  priority: SourcePriority;
  scrapeConfig?: ScrapeConfig | null;
  watermarkRemoval?: WatermarkRemovalConfig;
  proxyPoolId?: string | null;
}

export interface UpdateSourceInput {
  name?: string;
  baseUrl?: string;
  countryCode?: string | null;
  priority?: SourcePriority;
  scrapeConfig?: ScrapeConfig | null;
  watermarkRemoval?: WatermarkRemovalConfig;
  proxyPoolId?: string | null;
}

export interface DuplicateSourceInput {
  name: string;
  slug: string;
}

export interface SourceScheduleInput {
  enabled: boolean;
  intervalValue?: number;
  intervalUnit?: ScrapeIntervalUnit;
  revision: number;
}

export interface SourceExportInput {
  scope: "all" | "selected";
  sourceIds: string[];
}

export interface SourceImportInput {
  document: SourceTransferDocument;
  conflictActions: Record<string, "update" | "skip">;
}

export interface ScanTriggerResponse {
  taskId: string;
  sourceId: string;
  runId: string;
}

export function fetchSources(): Promise<Source[]> {
  return apiRequest<Source[]>("/sources");
}

export function fetchSourcesSummary(): Promise<SourcesSummary> {
  return apiRequest<SourcesSummary>("/sources/summary");
}

export function exportSources(input: SourceExportInput): Promise<SourceTransferDocument> {
  return apiRequest<SourceTransferDocument>("/sources/export", { method: "POST", body: input });
}

export function previewSourcesImport(document: unknown): Promise<SourceImportPreviewResult> {
  return apiRequest<SourceImportPreviewResult>("/sources/import/preview", {
    method: "POST",
    body: { document },
  });
}

export function importSources(input: SourceImportInput): Promise<SourceImportResult> {
  return apiRequest<SourceImportResult>("/sources/import", { method: "POST", body: input });
}

export function runSourceScan(id: string): Promise<ScanTriggerResponse> {
  return apiRequest<ScanTriggerResponse>(`/sources/${id}/scan`, { method: "POST" });
}

export function updateSourceSchedule(id: string, input: SourceScheduleInput): Promise<Source> {
  return apiRequest<Source>(`/sources/${id}/schedule`, { method: "PATCH", body: input });
}

export function pauseSource(id: string): Promise<void> {
  return apiRequest<void>(`/sources/${id}/pause`, { method: "POST" });
}

export function disableSource(id: string): Promise<void> {
  return apiRequest<void>(`/sources/${id}/disable`, { method: "POST" });
}

export function enableSource(id: string): Promise<void> {
  return apiRequest<void>(`/sources/${id}/enable`, { method: "POST" });
}

export function duplicateSource(id: string, input: DuplicateSourceInput): Promise<Source> {
  return apiRequest<Source>(`/sources/${id}/duplicate`, { method: "POST", body: input });
}

// Drill-down history for a single source (recent scrape_runs + their
// errors), used by the expandable row in SourcesPage.
export function fetchSourceRuns(id: string): Promise<ScrapeRun[]> {
  return apiRequest<ScrapeRun[]>(`/sources/${id}/runs`);
}

// Full detail including scrapeConfig, used to pre-fill the "Edit
// configuration" dialog (GET /sources only returns hasScrapeConfig, a
// boolean — not the config itself, which the plain list view doesn't need).
export function fetchSource(id: string): Promise<SourceDetail> {
  return apiRequest<SourceDetail>(`/sources/${id}`);
}

export function createSource(input: CreateSourceInput): Promise<Source> {
  return apiRequest<Source>("/sources", { method: "POST", body: input });
}

export function updateSource(id: string, input: UpdateSourceInput): Promise<Source> {
  return apiRequest<Source>(`/sources/${id}`, { method: "PATCH", body: input });
}

export function deleteSource(id: string): Promise<void> {
  return apiRequest<void>(`/sources/${id}`, { method: "DELETE" });
}

// Checks the source's public robots.txt for the configured user-agent —
// only robots.txt itself is fetched, no other content from the source.
export function checkSourceRobots(id: string): Promise<RobotsCheckResult> {
  return apiRequest<RobotsCheckResult>(`/sources/${id}/check-robots`, { method: "POST" });
}

// Dry-runs the source's scrape config against ONE real ad (nothing is
// saved to the DB) so an operator can verify selectors before a real scan.
export function testSourceConfig(
  id: string,
  scrapeConfig: ScrapeConfig,
  proxyPoolId: string | null,
): Promise<TestConfigResult> {
  return apiRequest<TestConfigResult>(`/sources/${id}/test-config`, {
    method: "POST",
    body: { scrapeConfig, proxyPoolId },
  });
}
