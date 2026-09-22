import { describeError } from "@/lib/errors";
import Icon from "./Icon";

// Shared error display, block form (a card/panel — not a table row, see
// ErrorRow in Table.tsx for that). Used wherever a query/mutation fails
// outside a table: dashboard panels, record detail tabs, forms.
export default function ErrorState({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const { title, description, retryable } = describeError(error);

  return (
    <div
      role="alert"
      className={`flex flex-col items-center justify-center gap-2 py-10 px-6 text-center ${className ?? ""}`}
    >
      <Icon name="error" className="text-error" size={28} />
      <p className="text-body-md font-semibold text-on-surface">{title}</p>
      <p className="text-body-md text-on-surface-variant max-w-sm">{description}</p>
      {retryable && onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 px-3 py-1.5 border border-border rounded text-label-sm text-on-surface hover:bg-surface-container-low transition-colors"
        >
          Riprova
        </button>
      )}
    </div>
  );
}
