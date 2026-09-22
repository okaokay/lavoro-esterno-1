import type { CustomFieldObject, CustomFieldValue } from "@/types";

function isObject(value: CustomFieldValue | CustomFieldObject): value is CustomFieldObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function ObjectValue({ value }: { value: CustomFieldObject }) {
  return (
    <dl className="grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-3 gap-y-1">
      {Object.entries(value).map(([key, item]) => (
        <div key={key} className="contents">
          <dt className="font-mono text-label-sm text-on-surface-variant break-words">{key}</dt>
          <dd className="break-all">{item}</dd>
        </div>
      ))}
    </dl>
  );
}

export default function CustomFieldValueDisplay({ value }: { value: CustomFieldValue }) {
  if (value === null || value === "" || (Array.isArray(value) && value.length === 0)) {
    return <span className="italic text-outline">Nessun valore trovato</span>;
  }
  if (Array.isArray(value)) {
    return (
      <ul className="space-y-2">
        {value.map((item, index) => (
          <li key={`${JSON.stringify(item)}-${index}`} className="whitespace-pre-line break-words">
            {isObject(item) ? <ObjectValue value={item} /> : item}
          </li>
        ))}
      </ul>
    );
  }
  if (isObject(value)) return <ObjectValue value={value} />;
  return <span className="whitespace-pre-line break-words">{value}</span>;
}
