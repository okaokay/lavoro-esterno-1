import { cn } from "@/lib/cn";

// Semantic pill badge with a leading dot, matching Healthy/Degraded/Offline,
// Ready/Processing/Failed etc. status chips across every mockup.
export type BadgeTone = "success" | "warning" | "error" | "info" | "neutral" | "primary";

const toneClasses: Record<BadgeTone, string> = {
  success: "bg-[#ecfdf5] text-[#065f46]",
  warning: "bg-[#fffbeb] text-[#b45309]",
  error: "bg-[#fef2f2] text-[#991b1b]",
  info: "bg-info/10 text-info",
  neutral: "bg-surface-container-high text-on-surface-variant border border-border",
  primary: "bg-primary/10 text-primary",
};

const dotClasses: Record<BadgeTone, string> = {
  success: "bg-success",
  warning: "bg-warning",
  error: "bg-error",
  info: "bg-info",
  neutral: "bg-outline",
  primary: "bg-primary",
};

export default function Badge({
  tone = "neutral",
  children,
  className,
  dot = true,
}: {
  tone?: BadgeTone;
  children: React.ReactNode;
  className?: string;
  dot?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium",
        toneClasses[tone],
        className,
      )}
    >
      {dot && <span className={cn("w-1.5 h-1.5 rounded-full", dotClasses[tone])} />}
      {children}
    </span>
  );
}
