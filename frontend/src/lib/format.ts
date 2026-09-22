/** Formattatori condivisi: output italiano e fuso orario Europe/Rome. */
const LOCALE = "it-IT";
const TIME_ZONE = "Europe/Rome";

export function formatDateTime(value?: string | Date | null): string {
  if (!value) return "—";
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : new Intl.DateTimeFormat(LOCALE, {
    dateStyle: "medium", timeStyle: "short", timeZone: TIME_ZONE,
  }).format(date);
}

export function formatDate(value?: string | Date | null): string {
  if (!value) return "—";
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : new Intl.DateTimeFormat(LOCALE, {
    dateStyle: "medium", timeZone: TIME_ZONE,
  }).format(date);
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat(LOCALE).format(value);
}

export function formatPercent(value: number, maximumFractionDigits = 1): string {
  return new Intl.NumberFormat(LOCALE, { style: "percent", maximumFractionDigits }).format(value);
}
