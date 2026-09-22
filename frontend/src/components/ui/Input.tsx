import type { InputHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  icon?: string;
  mono?: boolean;
}

// Text/search input, optionally with a leading Material icon (used for the
// login form and the phone search bar).
export default function Input({ icon, mono, className, ...props }: InputProps) {
  const input = (
    <input
      className={cn(
        "block w-full py-2 px-3 border border-outline-variant rounded bg-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container text-on-surface placeholder-outline-variant transition-colors outline-none",
        mono ? "font-mono text-mono-data" : "text-body-md",
        icon && "pl-9",
        className,
      )}
      {...props}
    />
  );

  if (!icon) return input;

  return (
    <div className="relative">
      <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-outline text-[18px] pointer-events-none">
        {icon}
      </span>
      {input}
    </div>
  );
}
