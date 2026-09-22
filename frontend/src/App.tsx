/** Mappa delle route pubbliche/protette e redirect di compatibilità della SPA. */
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import AppShell from "@/layout/AppShell";
import ProtectedRoute from "@/routes/ProtectedRoute";
import LoginPage from "@/routes/LoginPage";
import TwoFactorSetupPage from "@/routes/TwoFactorSetupPage";
import DashboardPage from "@/routes/DashboardPage";
import SearchPage from "@/routes/SearchPage";
import SourcesPage from "@/routes/SourcesPage";
import ExportsPage from "@/routes/ExportsPage";
import AdminPage from "@/routes/AdminPage";
import AISettingsPage from "@/routes/AISettingsPage";
import ProxySettingsPage from "@/routes/ProxySettingsPage";
import IngestionSettingsPage from "@/routes/IngestionSettingsPage";
import WebhookSettingsPage from "@/routes/WebhookSettingsPage";
import AccountPage from "@/routes/AccountPage";
import RecordDetailLayout from "@/routes/records/RecordDetailLayout";
import RecordOverviewTab from "@/routes/records/RecordOverviewTab";
import RecordOccurrencesTab from "@/routes/records/RecordOccurrencesTab";
import RecordMediaTab from "@/routes/records/RecordMediaTab";
import RecordAiSummaryTab from "@/routes/records/RecordAiSummaryTab";
import RecordHistoryTab from "@/routes/records/RecordHistoryTab";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      {/* Everything below requires an authenticated session */}
      <Route element={<ProtectedRoute />}>
        {/* Standalone (no sidebar): mandatory for Admin/Operator accounts
            without 2FA enrolled yet — ProtectedRoute redirects here from
            every other route until setup is completed. */}
        <Route path="/2fa-setup" element={<TwoFactorSetupPage />} />
        <Route element={<AppShell />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/search" element={<LegacySearchRedirect />} />
          {/* "Records" nav entry lands on the same search experience — there is
              no separate unfiltered browse view in the mockups. */}
          <Route path="/records" element={<SearchPage />} />
          <Route path="/records/:id" element={<RecordDetailLayout />}>
            <Route index element={<Navigate to="overview" replace />} />
            <Route path="overview" element={<RecordOverviewTab />} />
            <Route path="occurrences" element={<RecordOccurrencesTab />} />
            <Route path="media" element={<RecordMediaTab />} />
            <Route path="ai-summary" element={<RecordAiSummaryTab />} />
            <Route path="history" element={<RecordHistoryTab />} />
          </Route>
          <Route path="/sources" element={<SourcesPage />} />
          <Route path="/exports" element={<ExportsPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/settings/ai" element={<AISettingsPage />} />
          <Route path="/settings/proxies" element={<ProxySettingsPage />} />
          <Route path="/settings/ingestion" element={<IngestionSettingsPage />} />
          <Route path="/settings/webhooks" element={<WebhookSettingsPage />} />
          <Route path="/account" element={<AccountPage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

function LegacySearchRedirect() {
  const { search } = useLocation();
  return <Navigate to={`/records${search}`} replace />;
}
