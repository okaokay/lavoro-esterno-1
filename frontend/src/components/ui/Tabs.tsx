import { NavLink } from "react-router-dom";
import { cn } from "@/lib/cn";

export interface TabItem {
  to: string;
  label: string;
  icon?: string;
  end?: boolean;
}

// Router-driven tab strip used for the Record Detail page
// (Overview/Occurrences/Media/AI Summary/History) and Admin sub-sections.
export default function Tabs({ items }: { items: TabItem[] }) {
  return (
    <div className="border-b border-border flex gap-1 px-5">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-1.5 px-3 py-2.5 text-label-sm font-medium border-b-2 -mb-px transition-colors",
              isActive
                ? "border-primary text-primary"
                : "border-transparent text-on-surface-variant hover:text-on-surface",
            )
          }
        >
          {item.icon && <span className="material-symbols-outlined text-[16px]">{item.icon}</span>}
          {item.label}
        </NavLink>
      ))}
    </div>
  );
}
