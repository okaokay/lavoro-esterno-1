/** Raggruppa i campi dinamici di più fonti mantenendo visibile la provenienza. */
import type { CustomFieldGroup, CustomFieldValue } from "@/types";
import CustomFieldValueDisplay from "./CustomFieldValueDisplay";

interface AggregatedCustomFieldsProps {
  groups: CustomFieldGroup[];
  exclude?: string[];
}

function FieldValue({ value }: { value: CustomFieldValue }) {
  return <CustomFieldValueDisplay value={value} />;
}

export default function AggregatedCustomFields({
  groups,
  exclude = [],
}: AggregatedCustomFieldsProps) {
  const excluded = new Set(exclude);
  const visibleGroups = groups.filter((group) => !excluded.has(group.name));

  if (visibleGroups.length === 0) return null;

  return (
    <div className="space-y-5">
      {visibleGroups.map((group) => (
        <section key={group.name} className="rounded-md border border-border overflow-hidden">
          <h4 className="px-4 py-3 bg-surface-container-low text-label-md font-semibold text-on-surface break-all">
            {group.name}
          </h4>
          <div className="divide-y divide-border">
            {group.values.map((entry) => (
              <div
                key={`${entry.sourceId}-${entry.advertisementId}`}
                className="grid grid-cols-1 gap-2 px-4 py-3 md:grid-cols-[minmax(9rem,0.35fr)_1fr]"
              >
                <div className="flex flex-wrap items-start gap-2">
                  <span className="text-label-sm font-medium text-on-surface">{entry.sourceName}</span>
                  <span className="font-mono text-xs text-on-surface-variant">{entry.sourceCode}</span>
                  {entry.isCanonical && (
                    <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-primary">
                      Canonico
                    </span>
                  )}
                </div>
                <div className="text-body-md text-on-surface">
                  <FieldValue value={entry.value} />
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
