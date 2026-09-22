import { apiRequest } from "./client";
import type { ExportFilters, ExportJob, ExportType } from "@/types";

export function fetchExportJobs(): Promise<ExportJob[]> {
  return apiRequest<ExportJob[]>("/exports");
}

export interface CreateExportInput {
  type: ExportType;
  scope?: "selected" | "filters" | "all";
  recordIds?: string[];
  filters?: ExportFilters;
}

export function createExportJob(input: CreateExportInput): Promise<ExportJob> {
  return apiRequest<ExportJob>("/exports", {
    method: "POST",
    body: input,
  });
}

export function retryExportJob(id: string): Promise<ExportJob> {
  return apiRequest<ExportJob>(`/exports/${id}/retry`, { method: "POST" });
}

// The backend streams the file; we just resolve the signed URL to open/download.
export function getExportDownloadUrl(id: string): Promise<{ url: string; expiresAt: string | null }> {
  return apiRequest<{ url: string; expiresAt: string | null }>(`/exports/${id}/download`);
}
