import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "@/api/integrations";

export const useIngestionSettings = () => useQuery({ queryKey: ["settings", "ingestion"], queryFn: api.fetchIngestionSettings });
export function useUpdateIngestionSettings() { const client = useQueryClient(); return useMutation({ mutationFn: api.updateIngestionSettings, onSuccess: () => client.invalidateQueries({ queryKey: ["settings", "ingestion"] }) }); }
export const useSanitizeExisting = () => useMutation({ mutationFn: api.sanitizeExisting });
export const useWebhookEndpoints = () => useQuery({ queryKey: ["settings", "webhooks"], queryFn: api.fetchWebhookEndpoints });
export function useCreateWebhook() { const client = useQueryClient(); return useMutation({ mutationFn: api.createWebhookEndpoint, onSuccess: () => client.invalidateQueries({ queryKey: ["settings", "webhooks"] }) }); }
export function useUpdateWebhook() { const client = useQueryClient(); return useMutation({ mutationFn: ({ id, input }: { id: string; input: api.WebhookInput }) => api.updateWebhookEndpoint(id, input), onSuccess: () => client.invalidateQueries({ queryKey: ["settings", "webhooks"] }) }); }
export function useDeleteWebhook() { const client = useQueryClient(); return useMutation({ mutationFn: api.deleteWebhookEndpoint, onSuccess: () => client.invalidateQueries({ queryKey: ["settings", "webhooks"] }) }); }
