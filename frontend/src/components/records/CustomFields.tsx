/** Visualizza i campi dinamici di una singola occorrenza senza assumerne lo schema. */
import type { CustomFields as CustomFieldsMap } from "@/types";
import CustomFieldValueDisplay from "./CustomFieldValueDisplay";

interface CustomFieldsProps {
  fields: CustomFieldsMap;
  exclude?: string[];
  compact?: boolean;
}

function labelFor(name: string): string {
  return name
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function CustomFields({ fields, exclude = [], compact = false }: CustomFieldsProps) {
  const excluded = new Set(exclude);
  const entries = Object.entries(fields).filter(([name]) => !excluded.has(name));

  if (entries.length === 0) return null;

  return (
    <dl
      className={
        compact ? "grid grid-cols-1 md:grid-cols-2 gap-3" : "grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-5"
      }
    >
      {entries.map(([name, value]) => (
        <div
          key={name}
          className={compact ? "rounded border border-border bg-surface-container-lowest p-3" : "min-w-0"}
        >
          <dt className="text-label-sm text-on-surface-variant mb-1">{labelFor(name)}</dt>
          <dd className="text-body-md text-on-surface whitespace-pre-line break-words">
            <CustomFieldValueDisplay value={value} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
