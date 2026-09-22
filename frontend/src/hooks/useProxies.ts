/** Query e mutation React Query per la configurazione proxy Admin. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "@/api/proxies";

const key = ["admin", "proxies"] as const;
export const useProxyPools = (enabled = true) =>
  useQuery({ queryKey: [...key, "pools"], queryFn: api.fetchProxyPools, enabled });
export const useProxyEndpoints = () =>
  useQuery({ queryKey: [...key, "endpoints"], queryFn: api.fetchProxies });
export const useProxyFeeds = () => useQuery({ queryKey: [...key, "feeds"], queryFn: api.fetchProxyFeeds });

function useInvalidate() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: key });
}

export function useCreateProxyPool() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: api.createProxyPool, onSuccess: invalidate });
}
export function useUpdateProxyPool() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: Parameters<typeof api.updateProxyPool>[1] }) =>
      api.updateProxyPool(id, input),
    onSuccess: invalidate,
  });
}
export function useDeleteProxyPool() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: api.deleteProxyPool, onSuccess: invalidate });
}
export function useCreateProxy() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: api.createProxy, onSuccess: invalidate });
}
export function useUpdateProxy() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: Parameters<typeof api.updateProxy>[1] }) =>
      api.updateProxy(id, input),
    onSuccess: invalidate,
  });
}
export function useDeleteProxy() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: api.deleteProxy, onSuccess: invalidate });
}
export function useTestProxy() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, sourceId }: { id: string; sourceId: string }) => api.testProxy(id, sourceId),
    onSuccess: invalidate,
  });
}
export function useCreateProxyFeed() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: api.createProxyFeed, onSuccess: invalidate });
}
export function useUpdateProxyFeed() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: api.ProxyFeedInput }) => api.updateProxyFeed(id, input),
    onSuccess: invalidate,
  });
}
export function useDeleteProxyFeed() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: api.deleteProxyFeed, onSuccess: invalidate });
}
export function useSyncProxyFeed() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: api.syncProxyFeed, onSuccess: invalidate });
}
