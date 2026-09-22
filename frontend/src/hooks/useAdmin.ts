/** Query e mutation dell'area Admin con invalidazione mirata delle cache. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as adminApi from "@/api/admin";
import type { AIProviderName, UserRole } from "@/types";

const usersKey = ["admin", "users"] as const;

export function useAdminUsers() {
  return useQuery({ queryKey: usersKey, queryFn: adminApi.fetchAdminUsers });
}

export function useUpdateAdminUserRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, role }: { id: string; role: UserRole }) => adminApi.updateAdminUserRole(id, role),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}

export function useUpdateClearPhonePermission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      adminApi.updateClearPhonePermission(id, enabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}

export function useSuspendAdminUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: adminApi.suspendAdminUser,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}

export function useCreateAdminUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: adminApi.createAdminUser,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}

export function useResetAdminUserTwoFactor() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: adminApi.resetAdminUserTwoFactor,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}

export function useAuditLog() {
  return useQuery({ queryKey: ["admin", "audit-log"], queryFn: adminApi.fetchAuditLog });
}

export function useActivateAdminUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: adminApi.activateAdminUser,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}

const erasureKey = ["admin", "erasure-requests"] as const;

export function useErasureRequests() {
  return useQuery({
    queryKey: erasureKey,
    queryFn: adminApi.fetchErasureRequests,
    refetchInterval: (query) =>
      query.state.data?.some((item) => item.status === "pending" || item.status === "processing")
        ? 3000
        : false,
  });
}

export function useCreateErasureRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: adminApi.createErasureRequest,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: erasureKey }),
  });
}

export function useConfirmErasureRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: adminApi.confirmErasureRequest,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: erasureKey }),
  });
}

const aiSettingsKey = ["admin", "ai-settings"] as const;

export function useAISettings() {
  return useQuery({ queryKey: aiSettingsKey, queryFn: adminApi.fetchAISettings });
}

export function useUpdateAISettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: adminApi.updateAISettings,
    onSuccess: (data) => queryClient.setQueryData(aiSettingsKey, data),
  });
}

export function useUpdateAIProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ provider, input }: {
      provider: AIProviderName;
      input: Parameters<typeof adminApi.updateAIProvider>[1];
    }) => adminApi.updateAIProvider(provider, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: aiSettingsKey }),
  });
}

export function useAIProviderModels(provider: AIProviderName) {
  const queryClient = useQueryClient();
  const queryKey = ["admin", "ai-settings", provider, "models"] as const;
  const query = useQuery({
    queryKey,
    queryFn: () => adminApi.fetchAIProviderModels(provider),
    enabled: provider === "ollama",
    refetchInterval: (query) =>
      provider === "ollama" && (query.state.data?.models.length ?? 0) === 0 ? 5_000 : false,
  });
  const refresh = useMutation({
    mutationFn: () => adminApi.fetchAIProviderModels(provider, true),
    onSuccess: (result) => queryClient.setQueryData(queryKey, result),
  });
  return {
    ...query,
    refreshLive: refresh.mutate,
    isRefreshing: refresh.isPending,
    refreshError: refresh.error,
  };
}

export function useTestAIProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: adminApi.testAIProvider,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: aiSettingsKey }),
  });
}
