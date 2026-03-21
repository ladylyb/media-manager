import { apiGet } from "@/lib/api/client";
import type { HomePageData, LatestMetrics, SystemStatus } from "@/types";

export const getStatus = () => apiGet<SystemStatus>("/status");

export const getHome = () => apiGet<HomePageData>("/home");

export const getDashboardSummary = () => apiGet<Record<string, number>>("/dashboard-summary");

export const getLatestMetrics = () => apiGet<LatestMetrics>("/latest-metrics");

export async function fetchLogs(limit = 100): Promise<string[]> {
  const url = new URL("/logs", window.location.origin);
  url.searchParams.set("limit", String(limit));

  const response = await fetch(url.toString(), {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  return (await response.json()) as string[];
}
