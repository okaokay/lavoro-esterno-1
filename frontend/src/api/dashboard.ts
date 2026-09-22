/** Contratti HTTP delle viste aggregate, sempre vincolati a un intervallo esplicito. */
import { apiRequest } from "./client";
import type { ActivityEvent, DashboardKpis, DashboardRangeParams, ScrapingActivity, SourceHealthBreakdown } from "@/types";

function rangeQuery(range: DashboardRangeParams): string {
  const params = new URLSearchParams({ start: range.start, end: range.end });
  return `?${params.toString()}`;
}

export function fetchDashboardKpis(range: DashboardRangeParams): Promise<DashboardKpis> {
  return apiRequest<DashboardKpis>(`/dashboard/kpis${rangeQuery(range)}`);
}

export function fetchScrapingActivity(range: DashboardRangeParams): Promise<ScrapingActivity[]> {
  return apiRequest<ScrapingActivity[]>(`/dashboard/scraping-activity${rangeQuery(range)}`);
}

export function fetchSourceHealth(): Promise<SourceHealthBreakdown> {
  return apiRequest<SourceHealthBreakdown>("/dashboard/source-health");
}

export function fetchRecentActivity(range: DashboardRangeParams): Promise<ActivityEvent[]> {
  return apiRequest<ActivityEvent[]>(`/dashboard/activity${rangeQuery(range)}`);
}
