/** Pulsante del design system con varianti semantiche e dimensioni uniformi. */
import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const variantClasses: Record<Variant, string> = {
  primary: "bg-primary text-on-primary hover:bg-primary-container shadow-sm",
  secondary: "border border-border bg-surface-container-lowest text-on-surface-variant hover:bg-surface-container-low",
  ghost: "text-on-surface-variant hover:text-primary hover:bg-surface-container-low",
  danger: "border border-error/20 bg-error-container/30 text-error hover:bg-error-container/50",
};

const sizeClasses: Record<Size, string> = {
  sm: "px-3 py-1.5 text-label-sm font-label-sm",
  md: "px-4 py-2.5 text-label-sm font-label-sm",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export default function Button({ variant = "primary", size = "md", className, ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-DEFAULT font-medium transition-colors outline-none focus:ring-2 focus:ring-primary-container disabled:opacity-50 disabled:pointer-events-none",
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...props}
    />
  );
}
