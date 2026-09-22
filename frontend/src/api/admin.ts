import { apiRequest } from "./client";
import type {
  AdminUser, AIModelCatalog, AIProviderConfig, AIProviderName,
  AIProviderTestResult, AISettings, ErasureRequest, UserRole,
} from "@/types";

export function fetchAdminUsers(): Promise<AdminUser[]> {
  return apiRequest<AdminUser[]>("/admin/users");
}

export function updateAdminUserRole(id: string, role: UserRole): Promise<AdminUser> {
  return apiRequest<AdminUser>(`/admin/users/${id}`, { method: "PATCH", body: { role } });
}

export function updateClearPhonePermission(id: string, canViewClearPhone: boolean): Promise<AdminUser> {
  return apiRequest<AdminUser>(`/admin/users/${id}`, {
    method: "PATCH",
    body: { canViewClearPhone },
  });
}

export function suspendAdminUser(id: string): Promise<AdminUser> {
  return apiRequest<AdminUser>(`/admin/users/${id}/suspend`, { method: "POST" });
}

export interface CreateUserInput {
  email: string;
  password: string;
  role: UserRole;
}

// POST /admin/users requires the requesting admin to have 2FA enabled
// (`require_admin_with_2fa` server-side) — a 403 here most likely means
// that, not a generic permissions problem; see AdminPage.tsx's error copy.
export function createAdminUser(input: CreateUserInput): Promise<AdminUser> {
  return apiRequest<AdminUser>("/admin/users", { method: "POST", body: input });
}

// The backend response here is `{ id, mfa_enabled }` (snake_case, no
// CamelModel — see backend/app/schemas/auth.py:TwoFactorResetResponse),
// unlike every other admin.ts call: mapped explicitly here rather than
// changing an established backend contract just for this one field.
interface TwoFactorResetResponseDto {
  id: string;
  mfa_enabled: boolean;
}

export async function resetAdminUserTwoFactor(id: string): Promise<{ id: string; mfaEnabled: boolean }> {
  const dto = await apiRequest<TwoFactorResetResponseDto>(`/admin/users/${id}/reset-2fa`, {
    method: "POST",
  });
  return { id: dto.id, mfaEnabled: dto.mfa_enabled };
}

export interface AuditLogEntry {
  id: string;
  actor: string;
  action: string;
  target: string;
  occurredAt: string;
}

export function fetchAuditLog(): Promise<AuditLogEntry[]> {
  return apiRequest<AuditLogEntry[]>("/admin/audit-log");
}

export function activateAdminUser(id: string): Promise<AdminUser> {
  return apiRequest<AdminUser>(`/admin/users/${id}/activate`, { method: "POST" });
}

export function fetchErasureRequests(): Promise<ErasureRequest[]> {
  return apiRequest<ErasureRequest[]>("/privacy/erasure-requests");
}

export function createErasureRequest(input: {
  phone: string;
  reason: string;
  authorizationReference: string;
}): Promise<ErasureRequest> {
  return apiRequest<ErasureRequest>("/privacy/erasure-requests", { method: "POST", body: input });
}

export function confirmErasureRequest(id: string): Promise<ErasureRequest> {
  return apiRequest<ErasureRequest>(`/privacy/erasure-requests/${id}/confirm`, { method: "POST" });
}

export function fetchAISettings(): Promise<AISettings> {
  return apiRequest<AISettings>("/admin/ai-settings");
}

export function updateAISettings(input: {
  activeProvider?: AIProviderName;
  userDailyRequestLimit?: number;
  providerRequestsPerMinute?: number;
  globalDailyTokenBudget?: number;
  expectedRevision: number;
}): Promise<AISettings> {
  return apiRequest<AISettings>("/admin/ai-settings", { method: "PATCH", body: input });
}

export function updateAIProvider(
  provider: AIProviderName,
  input: {
    model?: string;
    enabled?: boolean;
    baseUrl?: string;
    apiKey?: string;
    clearCredential?: boolean;
    options?: Record<string, string>;
    expectedRevision: number;
  },
): Promise<AIProviderConfig> {
  return apiRequest<AIProviderConfig>(`/admin/ai-settings/providers/${provider}`, {
    method: "PATCH", body: input,
  });
}

export function fetchAIProviderModels(provider: AIProviderName, refresh = false): Promise<AIModelCatalog> {
  const suffix = refresh ? "?refresh=true" : "";
  return apiRequest<AIModelCatalog>(`/admin/ai-settings/providers/${provider}/models${suffix}`);
}

export function testAIProvider(provider: AIProviderName): Promise<AIProviderTestResult> {
  return apiRequest<AIProviderTestResult>(`/admin/ai-settings/providers/${provider}/test`, {
    method: "POST",
  });
}
