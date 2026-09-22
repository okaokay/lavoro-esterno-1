/** Stato client della console operativa: priorità, classifier, notifiche e diagnostica. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "@/api/operations";
import type { SourcePriority } from "@/types";

export function useSourcePriorities() {
  return useQuery({ queryKey: ["admin", "source-priorities"], queryFn: api.fetchSourcePriorities, refetchInterval: 3000 });
}
export function useUpdateSourcePriority() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ sourceId, priority }: { sourceId: string; priority: SourcePriority }) => api.updateSourcePriority(sourceId, priority),
    onSuccess: () => client.invalidateQueries({ queryKey: ["admin", "source-priorities"] }),
  });
}
export function useClassifierSettings() {
  return useQuery({ queryKey: ["admin", "classifier-settings"], queryFn: api.fetchClassifierSettings });
}
export function useUpdateClassifierSettings() {
  const client = useQueryClient();
  return useMutation({ mutationFn: api.updateClassifierSettings, onSuccess: (data) => client.setQueryData(["admin", "classifier-settings"], data) });
}
export function useReprocessClassifierMedia() {
  const client = useQueryClient();
  return useMutation({ mutationFn: api.reprocessClassifierMedia, onSuccess: () => client.invalidateQueries({ queryKey: ["admin", "classifier-settings"] }) });
}
export function useNotifications() {
  return useQuery({ queryKey: ["notifications"], queryFn: api.fetchNotifications, refetchInterval: 30000 });
}
export function useMarkNotificationRead() {
  const client = useQueryClient();
  return useMutation({ mutationFn: api.markNotificationRead, onSuccess: () => client.invalidateQueries({ queryKey: ["notifications"] }) });
}
export function useMarkAllNotificationsRead() {
  const client = useQueryClient();
  return useMutation({ mutationFn: api.markAllNotificationsRead, onSuccess: () => client.invalidateQueries({ queryKey: ["notifications"] }) });
}
export function useSystemStatus(enabled: boolean) {
  return useQuery({ queryKey: ["system-status"], queryFn: api.fetchSystemStatus, enabled, staleTime: 10000 });
}
