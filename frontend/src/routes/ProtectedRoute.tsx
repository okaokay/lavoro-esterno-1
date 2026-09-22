import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

// Gate for every authenticated route: while we're still resolving the
// session (page reload case) we render nothing rather than redirecting, to
// avoid a flash to /login for users who are actually still authenticated.
export default function ProtectedRoute() {
  const { user, isInitializing, requiresTwoFactorSetup } = useAuth();
  const location = useLocation();

  if (isInitializing) return null;

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Admin/Operator accounts without 2FA enrolled: every route except the
  // setup page itself redirects there (mirrors the backend's own 403 on any
  // other endpoint via get_current_user, app/security/deps.py).
  if (requiresTwoFactorSetup && location.pathname !== "/2fa-setup") {
    return <Navigate to="/2fa-setup" replace />;
  }

  return <Outlet />;
}
