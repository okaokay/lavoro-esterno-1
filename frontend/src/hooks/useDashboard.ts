/** Query dashboard indicizzate anche per finestra temporale, evitando cache incrociate. */
import { useQuery } from "@tanstack/react-query";
import { fetchDashboardKpis, fetchRecentActivity, fetchScrapingActivity, fetchSourceHealth } from "@/api/dashboard";
import { dashboardRangeForRequest, type DashboardRangeSelection } from "@/lib/dashboardRange";

function rangeKey(selection: DashboardRangeSelection): string[] {
  return selection.preset === "custom"
    ? [selection.preset, selection.range.start, selection.range.end]
    : [selection.preset];
}

export function useDashboardKpis(selection: DashboardRangeSelection) {
  return useQuery({
    queryKey: ["dashboard", "kpis", ...rangeKey(selection)],
    queryFn: () => fetchDashboardKpis(dashboardRangeForRequest(selection)),
  });
}

export function useScrapingActivity(selection: DashboardRangeSelection) {
  return useQuery({
    queryKey: ["dashboard", "scraping-activity", ...rangeKey(selection)],
    queryFn: () => fetchScrapingActivity(dashboardRangeForRequest(selection)),
    refetchInterval: 15000,
  });
}

export function useSourceHealth() {
  return useQuery({ queryKey: ["dashboard", "source-health"], queryFn: fetchSourceHealth });
}

export function useRecentActivity(selection: DashboardRangeSelection) {
  return useQuery({
    queryKey: ["dashboard", "activity", ...rangeKey(selection)],
    queryFn: () => fetchRecentActivity(dashboardRangeForRequest(selection)),
    refetchInterval: 30000,
  });
}
