import { apiRequest, tokenStorage } from "./client";
import type { LoginResult, User } from "@/types";

// Raw shapes returned by the backend before we map them to camelCase domain types.
interface LoginResponseDto {
  status: "authenticated" | "mfa_required" | "mfa_setup_required";
  access_token?: string;
  refresh_token?: string;
  mfa_token?: string;
  user?: { id: string; email: string; name: string; role: string; mfa_enabled: boolean; status: string };
  new_backup_codes?: string[];
}

function mapUser(dto: NonNullable<LoginResponseDto["user"]>): User {
  return {
    id: dto.id,
    email: dto.email,
    name: dto.name,
    role: dto.role as User["role"],
    mfaEnabled: dto.mfa_enabled,
    status: dto.status as User["status"],
  };
}

function mapLoginResponse(dto: LoginResponseDto): LoginResult {
  if (dto.status === "mfa_required") {
    return { status: "mfa_required", mfaToken: dto.mfa_token! };
  }
  if (dto.status === "mfa_setup_required") {
    return {
      status: "mfa_setup_required",
      tokens: { accessToken: dto.access_token!, refreshToken: dto.refresh_token! },
      user: mapUser(dto.user!),
    };
  }
  return {
    status: "authenticated",
    tokens: { accessToken: dto.access_token!, refreshToken: dto.refresh_token! },
    user: mapUser(dto.user!),
    newBackupCodes: dto.new_backup_codes,
  };
}

export async function login(email: string, password: string): Promise<LoginResult> {
  const dto = await apiRequest<LoginResponseDto>("/auth/login", {
    method: "POST",
    skipAuth: true,
    body: { email, password },
  });
  return mapLoginResponse(dto);
}

// Second step of the login flow: user submits a 6-digit TOTP code or a
// 10-character backup code alongside the short-lived mfaToken from /auth/login.
export async function loginWithTwoFactor(mfaToken: string, code: string): Promise<LoginResult> {
  const dto = await apiRequest<LoginResponseDto>("/auth/login-2fa", {
    method: "POST",
    skipAuth: true,
    body: { mfa_token: mfaToken, code },
  });
  return mapLoginResponse(dto);
}

export async function fetchCurrentUser(): Promise<User> {
  const dto = await apiRequest<NonNullable<LoginResponseDto["user"]>>("/auth/me");
  return mapUser(dto);
}

export async function logout(): Promise<void> {
  await apiRequest<void>("/auth/logout", {
    method: "POST",
    body: { refresh_token: tokenStorage.getRefreshToken() ?? undefined },
  });
}

export interface TwoFactorSetup {
  secret: string;
  qrCodeBase64: string;
  backupCodes: string[];
}

export async function setupTwoFactor(): Promise<TwoFactorSetup> {
  const dto = await apiRequest<{ secret: string; qr_code_base64: string; backup_codes: string[] }>(
    "/auth/setup-2fa",
    { method: "POST" },
  );
  return { secret: dto.secret, qrCodeBase64: dto.qr_code_base64, backupCodes: dto.backup_codes };
}

export async function verifyTwoFactorSetup(code: string): Promise<User> {
  const dto = await apiRequest<NonNullable<LoginResponseDto["user"]>>("/auth/verify-2fa", {
    method: "POST",
    body: { code },
  });
  return mapUser(dto);
}

export async function regenerateBackupCodes(code: string): Promise<string[]> {
  const dto = await apiRequest<{ backup_codes: string[] }>("/auth/2fa/backup-codes/regenerate", {
    method: "POST",
    body: { code },
  });
  return dto.backup_codes;
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await apiRequest<void>("/auth/change-password", {
    method: "POST",
    body: { current_password: currentPassword, new_password: newPassword },
  });
}
