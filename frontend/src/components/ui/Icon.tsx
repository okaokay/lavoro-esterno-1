import type { CSSProperties } from "react";

// Wraps a Material Symbols Outlined glyph. The font is loaded globally via
// index.html; this component just standardizes size/className usage.
export default function Icon({
  name,
  className,
  size = 20,
}: {
  name: string;
  className?: string;
  size?: number;
}) {
  const style: CSSProperties = { fontSize: size };
  return (
    <span className={cnIcon(className)} style={style} aria-hidden="true">
      {name}
    </span>
  );
}

function cnIcon(className?: string) {
  return ["material-symbols-outlined", className].filter(Boolean).join(" ");
}
