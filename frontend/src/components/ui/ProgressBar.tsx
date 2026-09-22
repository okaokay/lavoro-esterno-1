/** Barra di avanzamento accessibile con colori coerenti ai badge di stato. */
import { cn } from "@/lib/cn";
import type { BadgeTone } from "./Badge";

const barTone: Record<BadgeTone, string> = {
  success: "bg-success",
  warning: "bg-warning",
  error: "bg-error",
  info: "bg-info",
  neutral: "bg-outline",
  primary: "bg-primary",
};

export default function ProgressBar({
  value,
  tone = "primary",
  className,
}: {
  value: number;
  tone?: BadgeTone;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className={cn("w-full bg-surface-container-high rounded-full h-2", className)}>
      <div
        className={cn("h-2 rounded-full transition-all", barTone[tone])}
        style={{ width: `${clamped}%` }}
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
      />
    </div>
  );
}
