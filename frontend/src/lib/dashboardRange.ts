import type { DashboardRangeParams } from "@/types";

export type DashboardRangePreset = "24h" | "7d" | "30d" | "custom";

const ROME_TIME_ZONE = "Europe/Rome";
const MAX_RANGE_MS = 90 * 24 * 60 * 60 * 1000;
const PRESET_DURATION_MS: Record<Exclude<DashboardRangePreset, "custom">, number> = {
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
  "30d": 30 * 24 * 60 * 60 * 1000,
};

export interface DashboardRangeSelection {
  preset: DashboardRangePreset;
  range: DashboardRangeParams;
  warning?: string;
}

export function resolveDashboardRange(
  search: URLSearchParams,
  now = new Date(),
): DashboardRangeSelection {
  const rawPreset = search.get("range") ?? "24h";
  const preset: DashboardRangePreset = ["24h", "7d", "30d", "custom"].includes(rawPreset)
    ? (rawPreset as DashboardRangePreset)
    : "24h";

  if (preset === "custom") {
    const start = search.get("start");
    const end = search.get("end");
    if (start && end) {
      const startDate = new Date(start);
      const endDate = new Date(end);
      if (
        !Number.isNaN(startDate.valueOf()) &&
        !Number.isNaN(endDate.valueOf()) &&
        startDate < endDate &&
        endDate <= now &&
        endDate.valueOf() - startDate.valueOf() <= MAX_RANGE_MS
      ) {
        return { preset, range: { start: startDate.toISOString(), end: endDate.toISOString() } };
      }
    }
    return {
      preset: "24h",
      range: presetRange("24h", now),
      warning: "The saved dashboard interval is invalid. Showing the last 24 hours.",
    };
  }

  return { preset, range: presetRange(preset, now) };
}

export function presetRange(
  preset: Exclude<DashboardRangePreset, "custom">,
  now = new Date(),
): DashboardRangeParams {
  return {
    start: new Date(now.valueOf() - PRESET_DURATION_MS[preset]).toISOString(),
    end: now.toISOString(),
  };
}

export function dashboardRangeForRequest(
  selection: DashboardRangeSelection,
  now = new Date(),
): DashboardRangeParams {
  return selection.preset === "custom"
    ? selection.range
    : presetRange(selection.preset, now);
}

function datePartsInRome(date: Date): Record<string, string> {
  return Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: ROME_TIME_ZONE,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(date)
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value]),
  );
}

export function toRomeDateTimeInput(date: Date): string {
  const parts = datePartsInRome(date);
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

function offsetAt(date: Date): number {
  const parts = datePartsInRome(date);
  const displayedAsUtc = Date.UTC(
    Number(parts.year),
    Number(parts.month) - 1,
    Number(parts.day),
    Number(parts.hour),
    Number(parts.minute),
    Number(parts.second),
  );
  return displayedAsUtc - date.valueOf();
}

export function fromRomeDateTimeInput(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const desiredWallTime = Date.UTC(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3]),
    Number(match[4]),
    Number(match[5]),
  );
  let utcGuess = desiredWallTime;
  for (let pass = 0; pass < 3; pass += 1) {
    utcGuess = desiredWallTime - offsetAt(new Date(utcGuess));
  }
  const result = new Date(utcGuess);
  // Reject non-existent local times during the spring DST transition.
  return toRomeDateTimeInput(result) === value ? result : null;
}

export function validateCustomDashboardRange(
  startValue: string,
  endValue: string,
  now = new Date(),
): { range?: DashboardRangeParams; error?: string } {
  const start = fromRomeDateTimeInput(startValue);
  const end = fromRomeDateTimeInput(endValue);
  if (!start || !end) return { error: "Enter valid dates and times for Europe/Rome." };
  if (start >= end) return { error: "The start must be earlier than the end." };
  if (end > now) return { error: "The end cannot be in the future." };
  if (end.valueOf() - start.valueOf() > MAX_RANGE_MS) {
    return { error: "The interval cannot exceed 90 days." };
  }
  return { range: { start: start.toISOString(), end: end.toISOString() } };
}

export function formatRomeDateTime(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: ROME_TIME_ZONE,
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(iso));
}
