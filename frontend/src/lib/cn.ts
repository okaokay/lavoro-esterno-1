// Tiny className joiner (avoids pulling in clsx/tailwind-merge as a dependency
// for a scaffold this size — swap in `clsx`/`tailwind-merge` later if class
// conflicts start to matter).
export function cn(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(" ");
}
