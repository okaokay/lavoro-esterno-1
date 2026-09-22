/** Select nativa con lo stile e gli stati focus condivisi dal design system. */
import type { SelectHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export default function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "block py-2 px-3 border border-outline-variant rounded bg-surface text-body-md text-on-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container outline-none transition-colors",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}
