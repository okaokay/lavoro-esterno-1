/** Contratti HTTP per pool ed endpoint proxy; le credenziali non vengono mai lette. */
import { apiRequest } from "./client";
import type { ProxyEndpoint, ProxyFeed, ProxyPool, ProxyScheme, ProxyTestResult } from "@/types";

export const fetchProxyPools = () => apiRequest<ProxyPool[]>("/admin/proxy-pools");
export const fetchProxies = () => apiRequest<ProxyEndpoint[]>("/admin/proxies");
export const fetchProxyFeeds = () => apiRequest<ProxyFeed[]>("/admin/proxy-feeds");
export type ProxyFeedInput = {
  name: string;
  url: string;
  scheme: ProxyScheme;
  poolId: string;
  enabled: boolean;
  syncIntervalMinutes: number;
  headers: { key: string; value: string }[];
};
export const createProxyFeed = (input: ProxyFeedInput) =>
  apiRequest<ProxyFeed>("/admin/proxy-feeds", { method: "POST", body: input });
export const updateProxyFeed = (id: string, input: ProxyFeedInput) =>
  apiRequest<ProxyFeed>(`/admin/proxy-feeds/${id}`, { method: "PUT", body: input });
export const deleteProxyFeed = (id: string) =>
  apiRequest<void>(`/admin/proxy-feeds/${id}`, { method: "DELETE" });
export const syncProxyFeed = (id: string) =>
  apiRequest<{ taskId: string; queued: boolean }>(`/admin/proxy-feeds/${id}/sync`, { method: "POST" });
export const createProxyPool = (input: { name: string; enabled: boolean; proxyIds: string[] }) =>
  apiRequest<ProxyPool>("/admin/proxy-pools", { method: "POST", body: input });
export const updateProxyPool = (
  id: string,
  input: { name?: string; enabled?: boolean; proxyIds?: string[] },
) => apiRequest<ProxyPool>(`/admin/proxy-pools/${id}`, { method: "PATCH", body: input });
export const deleteProxyPool = (id: string) =>
  apiRequest<void>(`/admin/proxy-pools/${id}`, { method: "DELETE" });

export interface ProxyEndpointInput {
  name: string;
  scheme: ProxyScheme;
  host: string;
  port: number;
  username?: string;
  password?: string;
  enabled: boolean;
}

export const createProxy = (input: ProxyEndpointInput) =>
  apiRequest<ProxyEndpoint>("/admin/proxies", { method: "POST", body: input });
export const updateProxy = (id: string, input: Partial<ProxyEndpointInput> & { clearCredential?: boolean }) =>
  apiRequest<ProxyEndpoint>(`/admin/proxies/${id}`, { method: "PATCH", body: input });
export const deleteProxy = (id: string) => apiRequest<void>(`/admin/proxies/${id}`, { method: "DELETE" });
export const testProxy = (id: string, sourceId: string) =>
  apiRequest<ProxyTestResult>(`/admin/proxies/${id}/test`, {
    method: "POST",
    body: { sourceId },
  });
