// Deterministic color-by-name avatar (initials on a tinted background),
// used in Admin's user table and the Topbar account button.
const PALETTE = [
  "bg-primary/10 text-primary",
  "bg-secondary-container text-on-secondary-container",
  "bg-tertiary/10 text-tertiary",
  "bg-success/10 text-success",
  "bg-info/10 text-info",
];

function hashString(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i++) {
    hash = (hash << 5) - hash + value.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function Avatar({ name, size = 32 }: { name: string; size?: number }) {
  const tone = PALETTE[hashString(name) % PALETTE.length];
  return (
    <div
      className={`flex items-center justify-center rounded-full font-semibold shrink-0 ${tone}`}
      style={{ width: size, height: size, fontSize: size * 0.38 }}
    >
      {initials(name)}
    </div>
  );
}
