import { NavLink } from "react-router-dom";

const items = [["/settings/ai", "AI"], ["/settings/proxies", "Rotazione proxy"], ["/settings/ingestion", "Acquisizione"], ["/settings/webhooks", "Webhook"]] as const;

export default function SettingsTabs() {
  return <div className="flex flex-wrap gap-4 mt-3 border-b border-border">{items.map(([to, label]) => <NavLink key={to} to={to} className={({ isActive }) => `pb-2 ${isActive ? "border-b-2 border-primary text-primary" : "text-on-surface-variant"}`}>{label}</NavLink>)}</div>;
}
