import { apiRequest } from "./client";
import type { IngestionSettings, WebhookEndpoint } from "@/types";

export const fetchIngestionSettings = () => apiRequest<IngestionSettings>("/admin/ingestion-settings");
export const updateIngestionSettings = (input: { publishBatchSize: number; expectedRevision: number }) => apiRequest<IngestionSettings>("/admin/ingestion-settings", { method: "PATCH", body: input });
export const sanitizeExisting = () => apiRequest<{ taskId: string; queued: boolean }>("/admin/ingestion-settings/sanitize-existing", { method: "POST" });
export const fetchWebhookEndpoints = () => apiRequest<WebhookEndpoint[]>("/admin/webhook-endpoints");
export type WebhookInput = { name: string; url: string; enabled: boolean; allSources: boolean; sourceIds: string[]; phonePolicy: "clear" | "masked" | "excluded"; secret?: string; clearSecret?: boolean };
export const createWebhookEndpoint = (input: WebhookInput) => apiRequest<WebhookEndpoint>("/admin/webhook-endpoints", { method: "POST", body: input });
export const updateWebhookEndpoint = (id: string, input: WebhookInput) => apiRequest<WebhookEndpoint>(`/admin/webhook-endpoints/${id}`, { method: "PUT", body: input });
export const deleteWebhookEndpoint = (id: string) => apiRequest<void>(`/admin/webhook-endpoints/${id}`, { method: "DELETE" });
