/** Contratti HTTP della console operativa e amministrativa. */
import { apiRequest } from "./client";
import type { ClassifierSettings, NotificationList, SourcePriority, SourcePriorityConfig, SourcePriorityJob, SystemStatus } from "@/types";

export const fetchSourcePriorities = () => apiRequest<SourcePriorityConfig[]>("/admin/source-priorities");
export const updateSourcePriority = (sourceId: string, priority: SourcePriority) =>
  apiRequest<SourcePriorityJob>(`/admin/source-priorities/${sourceId}`, { method: "PATCH", body: { priority } });
export const fetchClassifierSettings = () => apiRequest<ClassifierSettings>("/admin/classifier-settings");
export const updateClassifierSettings = (input: { safeThreshold: number; explicitThreshold: number; expectedRevision: number }) =>
  apiRequest<ClassifierSettings>("/admin/classifier-settings", { method: "PATCH", body: input });
export const reprocessClassifierMedia = (scope: "failed" | "needs_review") =>
  apiRequest<{ scope: string; queued: number }>("/admin/classifier-settings/reprocess", { method: "POST", body: { scope } });
export const fetchNotifications = () => apiRequest<NotificationList>("/notifications");
export const markNotificationRead = (id: string) => apiRequest<void>(`/notifications/${id}/read`, { method: "POST" });
export const markAllNotificationsRead = () => apiRequest<void>("/notifications/read-all", { method: "POST" });
export const fetchSystemStatus = () => apiRequest<SystemStatus>("/system/status");
