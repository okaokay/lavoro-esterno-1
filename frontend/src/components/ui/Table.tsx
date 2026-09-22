import type { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from "react";
import { cn } from "@/lib/cn";
import { describeError } from "@/lib/errors";

// Minimal composable table primitives shared by every data-heavy page
// (Dashboard, Search, Sources, Exports, Admin, Record Occurrences).
// Header is sticky and rows highlight on hover per DESIGN.md ("Data Tables").

export function Table({ className, ...props }: HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="overflow-auto flex-1">
      <table className={cn("w-full text-left border-collapse", className)} {...props} />
    </div>
  );
}

export function THead({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead
      className={cn("sticky top-0 bg-surface-container-lowest z-10 shadow-[0_1px_0_#e2e8f0]", className)}
      {...props}
    />
  );
}

export function TBody({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("divide-y divide-border text-body-md", className)} {...props} />;
}

export function Tr({ className, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("hover:bg-surface-container-low transition-colors group", className)} {...props} />;
}

export function Th({ className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn("px-5 py-3 text-label-sm text-on-surface-variant font-semibold whitespace-nowrap", className)}
      {...props}
    />
  );
}

export function Td({ className, ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-5 py-2.5 align-middle", className)} {...props} />;
}

// Shown inside a <tbody> when a query returns zero rows.
export function EmptyRow({ colSpan, message }: { colSpan: number; message: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-5 py-12 text-center text-body-md text-on-surface-variant">
        {message}
      </td>
    </tr>
  );
}

// Shown inside a <tbody> while the underlying query is loading.
export function LoadingRow({ colSpan }: { colSpan: number }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-5 py-12 text-center text-body-md text-on-surface-variant">
        Caricamento…
      </td>
    </tr>
  );
}

// Shown inside a <tbody> when the underlying query failed. Pass `error`
// (the caught ApiError/exception) for a status-aware title+description+
// retry button via `describeError` (src/lib/errors.ts); `message` remains
// as a plain fallback for call sites that don't have the raw error handy.
export function ErrorRow({
  colSpan,
  error,
  message,
  onRetry,
}: {
  colSpan: number;
  error?: unknown;
  message?: string;
  onRetry?: () => void;
}) {
  const presentation = error !== undefined ? describeError(error) : undefined;

  return (
    <tr>
      <td colSpan={colSpan} className="px-5 py-10 text-center">
        <p className="text-body-md font-semibold text-error">{presentation?.title ?? "Errore"}</p>
        <p className="text-body-md text-on-surface-variant mt-1">
          {presentation?.description ?? message ?? "Si è verificato un errore."}
        </p>
        {presentation?.retryable && onRetry && (
          <button
            onClick={onRetry}
            className="mt-3 px-3 py-1.5 border border-border rounded text-label-sm text-on-surface hover:bg-surface-container-low transition-colors"
          >
            Riprova
          </button>
        )}
      </td>
    </tr>
  );
}
