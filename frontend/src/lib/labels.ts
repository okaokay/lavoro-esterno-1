/** Traduzione centralizzata di stati e ruoli restituiti dalle API. */
import i18n from "@/i18n";

const STATUS_KEYS: Record<string, string> = {
  pending: "status.pending", processing: "status.processing", running: "status.running",
  completed: "status.completed", failed: "status.failed", cancelled: "status.cancelled",
  ready: "status.ready", safe: "status.safe", explicit: "status.explicit",
  unclassified: "status.unclassified", needs_review: "status.needsReview",
  healthy: "status.healthy", degraded: "status.degraded", unavailable: "status.unavailable",
  offline: "status.offline", waiting: "status.waiting", paused: "status.paused",
  scheduled: "status.scheduled", manual: "status.manual", active: "common.active", inactive: "common.inactive",
  enabled: "common.enabled", disabled: "common.disabled", suspended: "status.suspended",
  invited: "status.invited", draft: "status.draft", confirmed: "status.confirmed",
};

export function statusLabel(value?: string | null): string {
  if (!value) return i18n.t("common.unknown");
  const key = STATUS_KEYS[value.toLowerCase()];
  return key ? i18n.t(key, { defaultValue: value }) : value;
}

const ROLE_LABELS: Record<string, string> = {
  admin: "Amministratore",
  operator: "Operatore",
  viewer: "Visualizzatore",
};

export function roleLabel(value?: string | null): string {
  if (!value) return i18n.t("common.unknown");
  return ROLE_LABELS[value.toLowerCase()] ?? value;
}

const CLASSIFIER_GROUP_LABELS: Record<string, string> = {
  classifications: "Classificazioni",
  processing: "Elaborazione",
  reviews: "Revisioni",
};

export function classifierGroupLabel(value: string): string {
  return CLASSIFIER_GROUP_LABELS[value] ?? value;
}
