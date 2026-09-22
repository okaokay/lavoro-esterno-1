import { NavLink } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import Icon from "@/components/ui/Icon";
import { cn } from "@/lib/cn";
import { useTranslation } from "react-i18next";

const NAV_ITEMS = [
  { to: "/dashboard", labelKey: "nav.dashboard", icon: "dashboard", adminOnly: false },
  { to: "/records", labelKey: "nav.records", icon: "database", adminOnly: false },
  { to: "/sources", labelKey: "nav.sources", icon: "source", adminOnly: false },
  { to: "/exports", labelKey: "nav.exports", icon: "cloud_download", adminOnly: false },
  { to: "/settings/ai", labelKey: "nav.settings", icon: "tune", adminOnly: true },
  { to: "/admin", labelKey: "nav.admin", icon: "admin_panel_settings", adminOnly: true },
] as const;

// Persistent left navigation (fixed width per DESIGN.md sidebar-width token).
// Highlights the active section using NavLink's isActive state.
export default function Sidebar() {
  const { logout, user } = useAuth();
  const { t } = useTranslation();

  return (
    <nav className="fixed left-0 top-0 h-screen w-sidebar-width bg-surface-container-lowest border-r border-border flex flex-col py-4 z-50 shadow-[0_0_15px_rgba(0,0,0,0.02)]">
      <div className="px-6 mb-8">
        <h1 className="text-headline-sm text-primary tracking-tight font-semibold">Lavoro Esterno</h1>
        <p className="text-label-sm text-on-surface-variant mt-1">{t("app.tagline")}</p>
      </div>

      <ul className="flex-1 px-4 space-y-1">
        {NAV_ITEMS.filter((item) => !item.adminOnly || user?.role === "admin").map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-4 py-2 rounded transition-colors duration-150",
                  isActive
                    ? "bg-secondary-container text-on-secondary-container font-semibold"
                    : "text-on-surface-variant hover:text-on-surface hover:bg-surface-container-low",
                )
              }
            >
              <Icon name={item.icon} className="text-xl" />
              <span className="text-body-md">{t(item.labelKey)}</span>
            </NavLink>
          </li>
        ))}
      </ul>

      <ul className="px-4 mt-auto space-y-1">
        <li>
          <button
            onClick={() => logout()}
            className="w-full flex items-center gap-3 px-4 py-2 rounded text-on-surface-variant hover:text-on-surface hover:bg-surface-container-low transition-colors duration-150"
          >
            <Icon name="logout" className="text-xl" />
            <span className="text-body-md">{t("nav.logout")}</span>
          </button>
        </li>
      </ul>
    </nav>
  );
}
