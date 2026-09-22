import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import * as authApi from "@/api/auth";
import { tokenStorage } from "@/api/client";
import type { LoginResult, User } from "@/types";

interface AuthContextValue {
  user: User | null;
  // True while we're checking for an existing session on first load, so
  // ProtectedRoute can avoid a flash-redirect to /login before we know.
  isInitializing: boolean;
  // Derived from `user`: roles for which 2FA is mandatory (admin/operator)
  // but who haven't completed setup yet. ProtectedRoute uses this to force
  // every route except /2fa-setup to redirect there — mirrors the same
  // enforcement the backend applies server-side (app/security/deps.py).
  requiresTwoFactorSetup: boolean;
  login: (email: string, password: string) => Promise<LoginResult>;
  verifyTwoFactor: (mfaToken: string, code: string) => Promise<string[] | undefined>;
  completeTwoFactorSetup: (code: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const ROLES_REQUIRING_MFA: User["role"][] = ["admin", "operator"];

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isInitializing, setIsInitializing] = useState(true);

  const refreshUser = useCallback(async () => {
    const me = await authApi.fetchCurrentUser();
    setUser(me);
  }, []);

  // On mount, if a refresh token is already in storage, silently resolve the
  // current user so a page reload doesn't bounce an already-logged-in user to /login.
  useEffect(() => {
    const bootstrap = async () => {
      if (!tokenStorage.getAccessToken()) {
        setIsInitializing(false);
        return;
      }
      try {
        await refreshUser();
      } catch {
        tokenStorage.clear();
      } finally {
        setIsInitializing(false);
      }
    };
    bootstrap();
  }, [refreshUser]);

  // apiRequest fires this event when a refresh attempt fails outright, so
  // the app can react centrally instead of every caller catching 401s.
  useEffect(() => {
    const onSessionExpired = () => setUser(null);
    window.addEventListener("lavoro-esterno:session-expired", onSessionExpired);
    return () => window.removeEventListener("lavoro-esterno:session-expired", onSessionExpired);
  }, []);

  // apiRequest fires this when ANY endpoint 403s with error_code
  // "mfa_setup_required" (defense in depth beyond the check on `login`'s own
  // response, e.g. if local user state was stale): re-fetch /auth/me, which
  // is always reachable regardless of enrollment status, to resync.
  useEffect(() => {
    const onMfaSetupRequired = () => {
      refreshUser().catch(() => undefined);
    };
    window.addEventListener("lavoro-esterno:mfa-setup-required", onMfaSetupRequired);
    return () => window.removeEventListener("lavoro-esterno:mfa-setup-required", onMfaSetupRequired);
  }, [refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    const result = await authApi.login(email, password);
    if (result.status === "authenticated" || result.status === "mfa_setup_required") {
      tokenStorage.setTokens(result.tokens.accessToken, result.tokens.refreshToken);
      setUser(result.user);
    }
    return result;
  }, []);

  const verifyTwoFactor = useCallback(async (mfaToken: string, code: string) => {
    const result = await authApi.loginWithTwoFactor(mfaToken, code);
    if (result.status === "authenticated" || result.status === "mfa_setup_required") {
      tokenStorage.setTokens(result.tokens.accessToken, result.tokens.refreshToken);
      setUser(result.user);
    }
    return result.status === "authenticated" ? result.newBackupCodes : undefined;
  }, []);

  const completeTwoFactorSetup = useCallback(async (code: string) => {
    const updated = await authApi.verifyTwoFactorSetup(code);
    setUser(updated);
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      tokenStorage.clear();
      setUser(null);
    }
  }, []);

  const requiresTwoFactorSetup = useMemo(
    () => !!user && ROLES_REQUIRING_MFA.includes(user.role) && !user.mfaEnabled,
    [user],
  );

  const value = useMemo(
    () => ({
      user,
      isInitializing,
      requiresTwoFactorSetup,
      login,
      verifyTwoFactor,
      completeTwoFactorSetup,
      logout,
      refreshUser,
    }),
    [user, isInitializing, requiresTwoFactorSetup, login, verifyTwoFactor, completeTwoFactorSetup, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
